#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$DIR/.pid"
MENUBAR_PID_FILE="$DIR/.menubar.pid"
PORT=8001

# If a previous PID is recorded but actually dead, clean it up
if [ -f "$PID_FILE" ]; then
  OLD_PID=$(cat "$PID_FILE" 2>/dev/null)
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "Video Transcriber is already running (PID $OLD_PID)"
    exit 0
  fi
  rm -f "$PID_FILE"
fi

# Free the port if a stale process owns it
if command -v lsof >/dev/null 2>&1; then
  STALE=$(lsof -ti :$PORT 2>/dev/null || true)
  if [ -n "${STALE:-}" ]; then
    echo "Killing stale process(es) on port $PORT: $STALE"
    echo "$STALE" | xargs kill 2>/dev/null || true
    sleep 1
  fi
fi

cd "$DIR"

# Use venv python if available, otherwise system python3
if [ -x "$DIR/.venv/bin/python" ]; then
  PY="$DIR/.venv/bin/python"
else
  PY="python3"
fi

# Start the web server
echo "Starting Video Transcriber at http://localhost:$PORT"
"$PY" -m uvicorn main:app --host 0.0.0.0 --port $PORT --app-dir "$DIR" >> "$DIR/app.log" 2>&1 &
PID=$!
echo $PID > "$PID_FILE"
echo "Server started (PID $PID)"

# Start the menu bar icon using the dedicated Homebrew-Python venv.
# Anaconda Python is not a Framework build and can't drive macOS GUI.
if [ -f "$DIR/menubar.py" ]; then
  GUI_PY="$DIR/.venv-menubar/bin/python"
  if [ ! -x "$GUI_PY" ]; then
    echo "Menu bar skipped — run: /opt/homebrew/bin/python3 -m venv $DIR/.venv-menubar && $DIR/.venv-menubar/bin/pip install rumps"
  else
    "$GUI_PY" "$DIR/menubar.py" >> "$DIR/app.log" 2>&1 &
    MENUBAR_PID=$!
    echo $MENUBAR_PID > "$MENUBAR_PID_FILE"
    echo "Menu bar started (PID $MENUBAR_PID)"
  fi
fi
