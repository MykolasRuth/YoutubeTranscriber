#!/usr/bin/env bash
set -e

# Ensure we're in the project directory
cd "$(dirname "$0")"

# Install/update dependencies
pip install -q -r requirements.txt

# Start the server
echo "Starting YouTube Transcriber at http://localhost:8001"
python3 -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload
