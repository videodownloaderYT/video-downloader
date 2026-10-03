"""
Video Downloader API (Flask + yt-dlp)

Endpoints
  GET  /health
  GET  /api/info?url=<youtube link>            -> title, duration, thumbnail, available qualities
  GET  /api/download?url=<link>&quality=720    -> the file itself (attachment); quality = 144..2160 or "audio"
  POST /api/info       {"url": "..."}          -> same as GET /api/info
  POST /api/download   {"url": "...", "quality": "720"}

Safety notes
  * The link is validated with a strict regex and only the 11 character video id is used,
    so nothing the user sends ever reaches a shell. yt-dlp is called through its Python API.
  * Files are written to a fresh temp folder per request and deleted after they are sent.
  * Small per-IP rate limit and a maximum video length.
"""
import mimetypes
import os
import re
import shutil
import tempfile
import threading
import time
from collections import defaultdict, deque

import yt_dlp
from flask import Flask, Response, jsonify, request, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

MAX_DURATION = int(os.getenv("MAX_DURATION_SECONDS", "3600"))   # refuse videos longer than this
RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_MIN", "10"))          # requests per minute per IP
HAS_FFMPEG = shutil.which("ffmpeg") is not None
QUALITIES = {"144", "240", "360", "480", "720", "1080", "1440", "2160"}

VIDEO_ID_RE = re.compile(
    r"^(?:https?://)?(?:www\.|m\.)?"
    r"(?:youtube\.com/(?:watch\?(?:\S*&)?v=|shorts/|embed/)|youtu\.be/)"
    r"([A-Za-z0-9_-]{11})(?:[&?#/]\S*)?$"
)


def extract_video_id(url):
    m = VIDEO_ID_RE.match((url or "").strip())
    return m.group(1) if m else None


# ---------------------------------------------------------------- rate limiting
_hits = defaultdict(deque)
_lock = threading.Lock()


def rate_limited(ip):
    now = time.time()
    with _lock:
        q = _hits[ip]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= RATE_LIMIT:
            return True
        q.append(now)
        return False


@app.before_request
def limit():
    if request.path.startswith("/api/") and rate_limited(request.remote_addr or "unknown"):
        return jsonify(error="Too many requests, please wait a minute."), 429


# ---------------------------------------------------------------- helpers
def get_params():
    data = request.get_json(silent=True) or {}
    url = data.get("url") or request.args.get("url")
    quality = str(data.get("quality") or request.args.get("quality") or "720").lower().replace("p", "")
    return url, quality


def canonical(video_id):
    return f"https://www.youtube.com/watch?v={video_id}"


def fetch_info(video_id):
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(canonical(video_id), download=False)


def available_heights(info):
    return sorted({f["height"] for f in info.get("formats", [])
                   if f.get("height") and f.get("vcodec") not in (None, "none")})


def fmt_duration(seconds):
    seconds = int(seconds or 0)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def build_options(quality, tmp):
    outtmpl = os.path.join(tmp, "%(title).80B [%(id)s].%(ext)s")
    base = {"quiet": True, "no_warnings": True, "noplaylist": True, "outtmpl": outtmpl,
            "restrictfilenames": False}
    if quality == "audio":
        if HAS_FFMPEG:
            base.update(format="bestaudio/best",
                        postprocessors=[{"key": "FFmpegExtractAudio", "preferredcodec": "mp3",
                                         "preferredquality": "192"}])
        else:
            base.update(format="bestaudio[ext=m4a]/bestaudio")
        return base
    h = int(quality)
    if HAS_FFMPEG:   # best video + best audio merged into one mp4 (this is how 1080p / 4K work)
        base.update(format=f"bestvideo[height<={h}]+bestaudio/best[height<={h}]",
                    merge_output_format="mp4")
    else:            # no ffmpeg: only single-file formats (usually up to 720p)
        base.update(format=f"best[height<={h}][ext=mp4]/best[height<={h}]")
    return base


def stream_file(path, tmp):
    """Send the file in chunks and delete the temp folder when the response ends
    (also when the user cancels the download)."""
    def generate():
        try:
            with open(path, "rb") as fh:
                while True:
                    chunk = fh.read(256 * 1024)
                    if not chunk:
                        break
                    yield chunk
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    name = os.path.basename(path)
    resp = Response(generate(), mimetype=mimetypes.guess_type(name)[0] or "application/octet-stream")
    resp.headers["Content-Length"] = str(os.path.getsize(path))
    resp.headers.set("Content-Disposition", "attachment", filename=name)
    resp.headers["Access-Control-Expose-Headers"] = "Content-Disposition, Content-Length"
    return resp


# ---------------------------------------------------------------- routes
@app.get("/")
def home():
    """Serve index.html if it is placed next to app.py."""
    here = os.path.dirname(os.path.abspath(__file__))
    if os.path.exists(os.path.join(here, "index.html")):
        return send_from_directory(here, "index.html")
    return jsonify(status="ok", docs="See README.md for the API endpoints.")


@app.get("/health")
def health():
    return jsonify(status="ok", ffmpeg=HAS_FFMPEG)


@app.route("/api/info", methods=["GET", "POST"])
def info():
    url, _ = get_params()
    video_id = extract_video_id(url)
    if not video_id:
        return jsonify(error="Invalid or missing YouTube link."), 400
    try:
        data = fetch_info(video_id)
    except Exception as exc:  # yt-dlp raises many different errors
        return jsonify(error=f"Could not fetch video info: {str(exc)[:200]}"), 502
    return jsonify(
        id=video_id,
        title=data.get("title"),
        author=data.get("uploader"),
        duration_seconds=data.get("duration"),
        duration=fmt_duration(data.get("duration")),
        views=data.get("view_count"),
        thumbnail=data.get("thumbnail"),
        qualities=[f"{h}p" for h in available_heights(data) if str(h) in QUALITIES] + ["audio"],
        max_duration_allowed=MAX_DURATION,
    )


@app.route("/api/download", methods=["GET", "POST"])
def download():
    url, quality = get_params()
    video_id = extract_video_id(url)
    if not video_id:
        return jsonify(error="Invalid or missing YouTube link."), 400
    if quality != "audio" and quality not in QUALITIES:
        return jsonify(error=f"quality must be one of {sorted(QUALITIES, key=int)} or 'audio'."), 400

    tmp = tempfile.mkdtemp(prefix="ytdl_")
    try:
        meta = fetch_info(video_id)
        if (meta.get("duration") or 0) > MAX_DURATION:
            raise ValueError(f"Video is longer than the allowed {MAX_DURATION // 60} minutes.")
        with yt_dlp.YoutubeDL(build_options(quality, tmp)) as ydl:
            ydl.download([canonical(video_id)])
        files = [f for f in os.listdir(tmp) if not f.endswith((".part", ".ytdl"))]
        if not files:
            raise RuntimeError("Download finished but no file was produced.")
        path = os.path.join(tmp, files[0])
        return stream_file(path, tmp)
    except ValueError as exc:
        shutil.rmtree(tmp, ignore_errors=True)
        return jsonify(error=str(exc)), 413
    except Exception as exc:
        shutil.rmtree(tmp, ignore_errors=True)
        return jsonify(error=f"Download failed: {str(exc)[:200]}"), 502


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")), debug=False)
