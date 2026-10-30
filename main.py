import os
import re
import json
import asyncio
import tempfile
import subprocess
import httpx
from contextlib import asynccontextmanager
from pathlib import Path

import yt_dlp
from faster_whisper import WhisperModel
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
from google import genai

import database
from url_utils import extract_supported_url, extract_youtube_id, is_tiktok_url, is_youtube_url

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Whisper model loaded once at startup and reused across requests
_whisper_model: WhisperModel | None = None

def get_whisper_model() -> WhisperModel:
    global _whisper_model
    if _whisper_model is None:
        # "small" balances speed and accuracy well for short TikTok clips.
        # Downloaded once (~244 MB) to ~/.cache/huggingface/hub on first run.
        _whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
    return _whisper_model


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


# ── URL detection ──────────────────────────────────────────────────────────────

# ── YouTube helpers ────────────────────────────────────────────────────────────

async def fetch_youtube_metadata(url: str) -> dict:
    oembed_url = f"https://www.youtube.com/oembed?url={url}&format=json"
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(oembed_url)
            resp.raise_for_status()
            data = resp.json()
            return {
                "title": data.get("title", "Unknown Title"),
                "author": data.get("author_name", "Unknown"),
                "thumbnail_url": data.get("thumbnail_url", ""),
            }
        except Exception:
            return {"title": "Unknown Title", "author": "Unknown", "thumbnail_url": ""}


def get_youtube_transcript(video_id: str) -> str:
    api = YouTubeTranscriptApi()
    try:
        fetched = api.fetch(video_id)
    except NoTranscriptFound:
        try:
            transcript_list = api.list(video_id)
            first = next(iter(transcript_list))
            fetched = first.fetch()
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"No transcript available: {e}")
    except TranscriptsDisabled:
        raise HTTPException(status_code=422, detail="Transcripts are disabled for this video.")
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to fetch transcript: {e}")

    return " ".join(snippet.text for snippet in fetched)


# ── TikTok helpers ─────────────────────────────────────────────────────────────

def _download_tiktok_sync(url: str, tmpdir: str) -> dict:
    """Download TikTok audio and return metadata + local file path. Runs in thread pool."""
    ydl_opts = {
        "format": "download/best[acodec!=none]/best",
        "outtmpl": os.path.join(tmpdir, "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    video_id = f"tt_{info.get('id', 'unknown')}"
    title = info.get("title") or info.get("description") or "TikTok Video"
    if len(title) > 120:
        title = title[:117] + "…"
    author = info.get("uploader") or info.get("creator") or "Unknown"
    thumbnail = info.get("thumbnail", "")

    files = [f for f in os.listdir(tmpdir) if not f.startswith(".")]
    if not files:
        raise RuntimeError("yt-dlp did not produce a file")
    audio_path = os.path.join(tmpdir, files[0])
    if not _has_audio_stream(audio_path):
        raise RuntimeError("Downloaded TikTok media does not contain an audio track.")

    return {
        "video_id": video_id,
        "title": title,
        "author": author,
        "thumbnail_url": thumbnail,
        "audio_path": audio_path,
    }


def _has_audio_stream(path: str) -> bool:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "default=nw=1:nk=1",
            path,
        ],
        text=True,
        capture_output=True,
        timeout=15,
    )
    return result.returncode == 0 and "audio" in result.stdout


def _transcribe_file_sync(audio_path: str) -> str:
    """Transcribe audio locally using Whisper. Runs in thread pool."""
    model = get_whisper_model()
    segments, _ = model.transcribe(audio_path, beam_size=5)
    text = " ".join(seg.text.strip() for seg in segments)
    return text.strip() or "[No speech detected]"


async def process_tiktok(url: str) -> dict:
    """Full TikTok pipeline: download → transcribe → return data dict."""
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            meta = await asyncio.to_thread(_download_tiktok_sync, url, tmpdir)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Failed to download TikTok video: {e}")

        try:
            transcript = await asyncio.to_thread(_transcribe_file_sync, meta["audio_path"])
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Failed to transcribe video: {e}")

    return {
        "video_id": meta["video_id"],
        "url": url,
        "title": meta["title"],
        "author": meta["author"],
        "thumbnail_url": meta["thumbnail_url"],
        "transcript": transcript,
    }


# ── Shared AI processing ───────────────────────────────────────────────────────

def generate_summary_and_highlights(transcript: str, title: str) -> tuple[str, list[str]]:
    if not GEMINI_API_KEY:
        return "No GEMINI_API_KEY configured.", ["Set GEMINI_API_KEY in .env to enable summaries."]

    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = f"""You are analyzing a video titled: "{title}"

Here is the full transcript:
<transcript>
{transcript[:15000]}
</transcript>

Please provide:
1. A concise summary (3-5 sentences) of what this video is about
2. 5-8 key highlights or takeaways as bullet points

Respond in this exact JSON format with no markdown code blocks:
{{
  "summary": "...",
  "highlights": ["...", "...", "..."]
}}"""

    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=prompt,
        config=genai.types.GenerateContentConfig(
            max_output_tokens=2048,
            temperature=0.4,
            response_mime_type="application/json",
        ),
    )

    text = response.text.strip()

    # Strip markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    # Try direct parse, then fall back to extracting the first {...} block
    candidates = [text]
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        candidates.append(m.group())

    for candidate in candidates:
        try:
            data = json.loads(candidate)
            return data.get("summary", ""), data.get("highlights", [])
        except (json.JSONDecodeError, ValueError):
            pass

    return text, []


def safe_summary_and_highlights(transcript: str, title: str) -> tuple[str, list[str]]:
    """Wrap the Gemini call so a transient AI failure never discards the transcript.

    The transcript is the expensive, valuable output; if Gemini is down (503),
    rate-limited (429), or otherwise errors, return a placeholder summary instead
    of failing the whole request.
    """
    try:
        return generate_summary_and_highlights(transcript, title)
    except Exception as e:
        err = str(e)
        if "429" in err or "RESOURCE_EXHAUSTED" in err or "quota" in err.lower():
            reason = "Gemini quota exceeded (free tier allows ~20 requests/day)."
        elif "503" in err or "UNAVAILABLE" in err:
            reason = "Gemini is temporarily overloaded (503). Try again shortly."
        else:
            reason = f"AI service error: {err}"
        return f"(Summary unavailable — {reason} Transcript is still available above.)", []


# ── Request / response models ──────────────────────────────────────────────────

class ProcessRequest(BaseModel):
    url: str


class SaveRequest(BaseModel):
    video_id: str
    url: str
    title: str
    author: str
    thumbnail_url: str
    transcript: str
    summary: str
    highlights: list[str]


class ChatMessage(BaseModel):
    role: str  # "user" or "model"
    content: str


class ChatRequest(BaseModel):
    transcript: str
    history: list[ChatMessage]
    message: str


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return FileResponse("static/index.html")


@app.post("/api/process")
async def process_video(req: ProcessRequest):
    url = extract_supported_url(req.url)

    if is_tiktok_url(url):
        data = await process_tiktok(url)
    elif is_youtube_url(url):
        try:
            video_id = extract_youtube_id(url)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        metadata = await fetch_youtube_metadata(url)
        transcript = get_youtube_transcript(video_id)
        data = {
            "video_id": video_id,
            "url": url,
            "title": metadata["title"],
            "author": metadata["author"],
            "thumbnail_url": metadata["thumbnail_url"],
            "transcript": transcript,
        }
    else:
        raise HTTPException(status_code=400, detail="Only YouTube and TikTok URLs are supported.")

    summary, highlights = safe_summary_and_highlights(data["transcript"], data["title"])
    return {**data, "summary": summary, "highlights": highlights}


@app.post("/api/save")
async def save_video(req: SaveRequest):
    return database.save_video(
        video_id=req.video_id,
        url=req.url,
        title=req.title,
        author=req.author,
        thumbnail_url=req.thumbnail_url,
        transcript=req.transcript,
        summary=req.summary,
        highlights=req.highlights,
    )


@app.post("/api/process-save")
async def process_and_save_video(req: ProcessRequest):
    """Single endpoint used by the menu bar: process + save atomically."""
    url = extract_supported_url(req.url)

    if is_tiktok_url(url):
        data = await process_tiktok(url)
    elif is_youtube_url(url):
        try:
            video_id = extract_youtube_id(url)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        metadata = await fetch_youtube_metadata(url)
        transcript = get_youtube_transcript(video_id)
        data = {
            "video_id": video_id,
            "url": url,
            "title": metadata["title"],
            "author": metadata["author"],
            "thumbnail_url": metadata["thumbnail_url"],
            "transcript": transcript,
        }
    else:
        raise HTTPException(status_code=400, detail="Only YouTube and TikTok URLs are supported.")

    summary, highlights = safe_summary_and_highlights(data["transcript"], data["title"])
    full = {**data, "summary": summary, "highlights": highlights}

    return database.save_video(
        video_id=full["video_id"],
        url=full["url"],
        title=full["title"],
        author=full["author"],
        thumbnail_url=full["thumbnail_url"],
        transcript=full["transcript"],
        summary=full["summary"],
        highlights=full["highlights"],
    )


@app.get("/api/videos")
async def list_videos():
    return database.list_videos()


@app.get("/api/videos/{video_id}")
async def get_video(video_id: str):
    video = database.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


@app.delete("/api/videos/{video_id}")
async def delete_video(video_id: str):
    deleted = database.delete_video(video_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Video not found")
    return {"deleted": True}


class SaveChatsRequest(BaseModel):
    messages: list[ChatMessage]


@app.post("/api/videos/{video_id}/chats")
async def save_chats(video_id: str, req: SaveChatsRequest):
    database.save_chats(video_id, [m.model_dump() for m in req.messages])
    return {"saved": True}


@app.get("/api/videos/{video_id}/chats")
async def get_chats(video_id: str):
    return database.get_chats(video_id)


@app.post("/api/chat")
async def chat(req: ChatRequest):
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=400, detail="No GEMINI_API_KEY configured in .env")

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)

        system_context = f"""You are a knowledgeable, conversational assistant. Answer questions using your own reasoning, knowledge, and judgment — just like a smart friend would.

The user is watching a video. Here is its transcript for reference:

<transcript>
{req.transcript[:20000]}
</transcript>

Use the transcript when the question is about the video. For everything else, answer freely from your own knowledge. Be direct and helpful."""

        history = [
            genai.types.Content(
                role=msg.role,
                parts=[genai.types.Part(text=msg.content)],
            )
            for msg in req.history
        ]

        chat_session = client.chats.create(
            model="gemini-2.5-flash-lite",
            history=history,
            config=genai.types.GenerateContentConfig(
                system_instruction=system_context,
                max_output_tokens=8192,
                temperature=0.7,
            ),
        )

        response = chat_session.send_message(req.message)
        return {"reply": response.text}

    except Exception as e:
        err_str = str(e)
        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
            raise HTTPException(
                status_code=429,
                detail="Gemini API quota exceeded. The free tier allows 20 requests/day for this model. Try again tomorrow or upgrade your Google AI plan.",
            )
        raise HTTPException(status_code=500, detail=err_str)
