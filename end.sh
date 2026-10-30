#!/usr/bin/env bash

DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$DIR/.pid"
PORT=8001

# Kill via PID file if available
if [ -f "$PID_FILE" ]; then
  PID=$(cat "$PID_FILE" 2>/dev/null)
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    kill "$PID" 2>/dev/null
    echo "Stopped Video Transcriber (PID $PID)"
  fi
  rm -f "$PID_FILE"
fi

# Also kill anything matching this project's directory (catches restarts /
# orphans / the uvicorn reloader's child processes that aren't in the .pid)
pgrep -f "$DIR" 2>/dev/null | xargs kill 2>/dev/null

# And anything still holding the port
if command -v lsof >/dev/null 2>&1; then
  PORT_PIDS=$(lsof -ti :$PORT 2>/dev/null || true)
  if [ -n "${PORT_PIDS:-}" ]; then
    echo "$PORT_PIDS" | xargs kill 2>/dev/null
  fi
fi

echo "Video Transcriber stopped."
