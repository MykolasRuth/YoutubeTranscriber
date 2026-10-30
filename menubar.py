#!/usr/bin/env python3
"""macOS menu bar app for Video Transcriber.

Uses osascript for all dialogs and notifications so it works with any
Python build (including Anaconda, which is not a Framework Python).
"""
import json
import subprocess
import threading
import urllib.request
import urllib.error

import rumps

API_URL = "http://localhost:8001"


# ── osascript helpers (work on any Python build) ────────────────────────────

def _run_apple(script: str) -> tuple[str, int]:
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return r.stdout.strip(), r.returncode


def ask_url() -> str | None:
    """Show a native macOS input dialog. Returns the URL or None if cancelled."""
    out, code = _run_apple(
        'set x to text returned of '
        '(display dialog "Paste a YouTube or TikTok URL:" '
        'default answer "" '
        'with title "Video Transcriber" '
        'buttons {"Cancel", "Save"} '
        'default button "Save")'
    )
    return out.strip() if code == 0 and out.strip() else None


def notify(title: str, message: str) -> None:
    _run_apple(f'display notification "{message}" with title "{title}"')


# ── background processing ───────────────────────────────────────────────────

def _post(path: str, payload: dict, timeout: int = 180) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{API_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def process_and_save(url: str) -> None:
    notify("Video Transcriber", "Processing video…")
    try:
        result = _post("/api/process-save", {"url": url}, timeout=300)
        title = result.get("title") or "Video"
        notify("Video Transcriber", f'Saved: {title[:60]}')
    except urllib.error.URLError:
        notify("Video Transcriber", "Error: app server is not running.")
    except Exception as e:
        notify("Video Transcriber", f"Error: {str(e)[:80]}")


# ── server heartbeat ────────────────────────────────────────────────────────

def _heartbeat_loop(interval: int = 10) -> None:
    """Poll the server; quit only after 3 consecutive failures."""
    import time
    failures = 0
    while True:
        time.sleep(interval)
        try:
            urllib.request.urlopen(f"{API_URL}/api/videos", timeout=5)
            failures = 0
        except Exception:
            failures += 1
            if failures >= 3:
                rumps.quit_application()
                return


# ── menu bar app ────────────────────────────────────────────────────────────

class VideoTranscriberApp(rumps.App):
    def __init__(self):
        super().__init__("▶")
        self.menu = ["Save video…", "Open app"]
        threading.Thread(target=_heartbeat_loop, daemon=True).start()

    @rumps.clicked("Save video…")
    def save_video(self, _):
        url = ask_url()
        if url:
            threading.Thread(target=process_and_save, args=(url,), daemon=True).start()

    @rumps.clicked("Open app")
    def open_app(self, _):
        subprocess.Popen(["open", API_URL])


if __name__ == "__main__":
    # Hide from Dock — menu bar only
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    except Exception:
        pass
    VideoTranscriberApp().run()
