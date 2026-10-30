import sqlite3
import json
import os
from datetime import datetime
from pathlib import Path

DB_PATH = Path(os.environ.get("VIDEOS_DB_PATH") or Path(__file__).parent / "videos.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL UNIQUE,
            url TEXT NOT NULL,
            title TEXT,
            author TEXT,
            thumbnail_url TEXT,
            transcript TEXT,
            summary TEXT,
            highlights TEXT,
            saved_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            position INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def save_video(
    video_id: str,
    url: str,
    title: str,
    author: str,
    thumbnail_url: str,
    transcript: str,
    summary: str,
    highlights: list[str],
) -> dict:
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO videos
                (video_id, url, title, author, thumbnail_url, transcript, summary, highlights, saved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(video_id) DO UPDATE SET
                title=excluded.title,
                author=excluded.author,
                thumbnail_url=excluded.thumbnail_url,
                transcript=excluded.transcript,
                summary=excluded.summary,
                highlights=excluded.highlights,
                saved_at=excluded.saved_at
            """,
            (
                video_id, url, title, author, thumbnail_url,
                transcript, summary, json.dumps(highlights),
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM videos WHERE video_id = ?", (video_id,)
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def save_chats(video_id: str, messages: list[dict]) -> None:
    conn = get_connection()
    try:
        conn.execute("DELETE FROM chats WHERE video_id = ?", (video_id,))
        for i, msg in enumerate(messages):
            conn.execute(
                "INSERT INTO chats (video_id, role, content, position) VALUES (?, ?, ?, ?)",
                (video_id, msg["role"], msg["content"], i),
            )
        conn.commit()
    finally:
        conn.close()


def get_chats(video_id: str) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT role, content FROM chats WHERE video_id = ? ORDER BY position",
            (video_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_videos() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM videos ORDER BY saved_at DESC"
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_video(video_id: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM videos WHERE video_id = ?", (video_id,)
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def delete_video(video_id: str) -> bool:
    conn = get_connection()
    try:
        conn.execute("DELETE FROM chats WHERE video_id = ?", (video_id,))
        cursor = conn.execute("DELETE FROM videos WHERE video_id = ?", (video_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    if d.get("highlights"):
        try:
            d["highlights"] = json.loads(d["highlights"])
        except (json.JSONDecodeError, TypeError):
            d["highlights"] = []
    return d
