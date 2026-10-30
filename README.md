# YouTube Transcriber

A small self-hosted web app that turns a YouTube or TikTok link into a transcript, a summary and key points, saves it to a searchable local library, and lets you chat about the video.

- **YouTube:** pulls the video's captions with `youtube-transcript-api`, so it's fast and needs no download.
- **TikTok:** downloads the clip with `yt-dlp` and transcribes it on your own machine with [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (the `small` model on CPU).
- **Summary, highlights and chat:** Google Gemini writes a 3–5 sentence summary and 5–8 key takeaways, and answers questions about a saved video.
- **Library:** everything is stored in SQLite (`videos.db`), with saved chat history per video.
- **Runs anywhere:** a FastAPI backend with a single-page front end (`static/index.html`), Docker Compose, and a macOS menu-bar app (`menubar.py`) to start and stop it.

## Setup

```bash
cp .env.example .env            # add your Gemini API key (free tier works)
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./start.sh                      # serves http://localhost:8001; ./end.sh stops it
```

Or with Docker: `docker compose up -d --build` (data is kept in `./data`).

The Whisper model (about 480 MB) downloads on the first TikTok transcription.

## Tests

```bash
.venv/bin/python -m unittest discover -p "test_*.py"
```
