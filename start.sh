#!/usr/bin/env bash
cd "$(dirname "$0")"
command -v ffmpeg >/dev/null || echo "[!] ffmpeg not found (needed for 1080p/4K and mp3): brew install ffmpeg / apt install ffmpeg"
python3 -m pip install --upgrade -r requirements.txt yt-dlp
(sleep 2; (xdg-open http://localhost:8000 || open http://localhost:8000) >/dev/null 2>&1) &
python3 app.py
