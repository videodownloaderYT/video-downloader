# Video Downloader API

Small Flask API on top of yt-dlp. Give it a YouTube link, get info or the video file back.

## Setup

```bash
pip install -r requirements.txt
# ffmpeg is needed for 1080p / 4K and mp3 (apt install ffmpeg, brew install ffmpeg, or ffmpeg.org)
python app.py                     # development, port 8000
gunicorn -w 2 -b 0.0.0.0:8000 --timeout 300 app:app   # production
```

Keep yt-dlp updated, YouTube changes often: `pip install -U yt-dlp`

## Endpoints

| Endpoint | Method | What it does |
|---|---|---|
| `/health` | GET | Server check, tells if ffmpeg is found |
| `/api/info?url=LINK` | GET or POST | Title, author, duration, thumbnail, available qualities |
| `/api/download?url=LINK&quality=720` | GET or POST | Sends the video file; `quality` is 144, 240, 360, 480, 720, 1080, 1440, 2160 or `audio` (mp3) |

Accepted links: `youtube.com/watch?v=`, `youtu.be/`, `youtube.com/shorts/`, `youtube.com/embed/`.

### Examples

```bash
curl "http://localhost:8000/api/info?url=https://www.youtube.com/watch?v=VIDEO_ID"

curl -OJ "http://localhost:8000/api/download?url=https://www.youtube.com/watch?v=VIDEO_ID&quality=720"

curl -X POST http://localhost:8000/api/download \
  -H "Content-Type: application/json" \
  -d '{"url":"https://youtu.be/VIDEO_ID","quality":"1080"}' -OJ
```

### From a website (JavaScript)

```js
const API = "http://localhost:8000";
const link = "https://www.youtube.com/watch?v=VIDEO_ID";

// 1. info and qualities
const info = await (await fetch(`${API}/api/info?url=${encodeURIComponent(link)}`)).json();

// 2. download: simplest is to point the browser at the URL
window.location = `${API}/api/download?url=${encodeURIComponent(link)}&quality=720`;
```

## Settings (environment variables)

| Name | Default | Meaning |
|---|---|---|
| `PORT` | 8000 | Port |
| `MAX_DURATION_SECONDS` | 3600 | Longer videos are refused |
| `RATE_LIMIT_PER_MIN` | 10 | Requests per minute per IP |

## Notes

* The link is checked with a strict pattern and only the 11 character video id is used. Nothing from the user goes to a shell.
* Every download uses its own temp folder, which is deleted after the file is sent.
* Without ffmpeg only single-file formats work (about 720p) and `audio` returns m4a.
* Downloading from YouTube is against YouTube's Terms of Service. Check this before running a public site, because ad networks and hosts may suspend accounts for it.
* Servers in datacenters are sometimes blocked by YouTube. If downloads fail with a sign-in or bot message, that is the cause, not the code.
