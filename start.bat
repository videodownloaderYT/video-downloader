@echo off
title Video Downloader
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python is not installed. Install it from https://www.python.org/downloads/ and tick "Add Python to PATH".
  pause
  exit /b 1
)

where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo.
  echo [!] ffmpeg not found. 1080p/4K and mp3 need it.
  echo     Install once with:  winget install Gyan.FFmpeg   then close and reopen this file.
  echo.
)

echo Installing / updating packages...
python -m pip install --upgrade -r requirements.txt
python -m pip install --upgrade yt-dlp

echo Starting server...
start "" http://localhost:8000
python app.py
pause
