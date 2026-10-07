import os
import sys
import subprocess
import re
import json
import time
import urllib.request
import urllib.parse
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

app = FastAPI(title="RetroPod Audio Cloud Bridge", version="1.0.0")

# Enable full CORS for Android mobile clients and Web browsers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Range", "Content-Length", "Accept-Ranges"]
)

STREAM_CACHE = {}

def parse_spotify_url(url: str):
    m = re.search(r'spotify\.com/(?:intl-[a-z]+/)?(playlist|album|track)/([a-zA-Z0-9]+)', url)
    if not m:
        return None
    entity_type, entity_id = m.group(1), m.group(2)
    embed_url = f"https://open.spotify.com/embed/{entity_type}/{entity_id}"
    req = urllib.request.Request(embed_url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    })
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read().decode('utf-8', errors='replace')
        match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
        if not match:
            return None
        data = json.loads(match.group(1))
        entity = data.get("props", {}).get("pageProps", {}).get("state", {}).get("data", {}).get("entity", {})
        title = entity.get("title") or entity.get("name") or "Spotify Playlist"
        cover = entity.get("coverArt", {}).get("sources", [{}])[-1].get("url", "")
        
        tracks = []
        raw_list = entity.get("trackList", [])
        if not raw_list and entity_type == "track":
            raw_list = [entity]
        for idx, item in enumerate(raw_list):
            t_title = item.get("title") or item.get("name") or "Unknown Title"
            t_artist = item.get("subtitle") or item.get("artists", "")
            if isinstance(t_artist, list):
                t_artist = ", ".join([a.get("name", "") if isinstance(a, dict) else str(a) for a in t_artist])
            t_duration = int(item.get("duration") or 0) // 1000
            q = f"{t_artist} - {t_title}" if t_artist else t_title
            tid = f"sp_{item.get('uri', '').split(':')[-1] or idx}"
            path = f"/api/stream-audio?q={urllib.parse.quote(q)}&id={urllib.parse.quote(tid)}"
            tracks.append({
                "id": tid,
                "title": t_title,
                "artist": t_artist,
                "album": title,
                "duration": t_duration,
                "has_art": bool(cover),
                "artwork": cover,
                "query": q,
                "path": path,
                "isOnlineStream": True,
                "platform": "Spotify"
            })
        return {
            "platform": "Spotify",
            "title": title,
            "artwork": cover,
            "tracks": tracks
        }
    except Exception as e:
        print("Spotify parser error:", e)
        return None

def parse_apple_music_url(url: str):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9"
    })
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read().decode('utf-8', errors='replace')
        blocks = re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.DOTALL)
        for block in blocks:
            try:
                data = json.loads(block)
                if data.get('@type') in ('MusicPlaylist', 'MusicAlbum', 'MusicRecording'):
                    title = data.get('name') or "Apple Music Playlist"
                    raw_tracks = data.get('track', [])
                    if not raw_tracks and data.get('@type') == 'MusicRecording':
                        raw_tracks = [data]
                    tracks = []
                    for idx, t in enumerate(raw_tracks):
                        t_name = t.get('name') or 'Unknown Title'
                        by = t.get('byArtist', {})
                        t_artist = by.get('name') if isinstance(by, dict) else str(by)
                        t_thumb = t.get('thumbnailUrl') or ''
                        dur_str = t.get('duration') or ''
                        dur_sec = 0
                        dur_match = re.match(r'PT(?:(\d+)M)?(?:(\d+)S)?', dur_str)
                        if dur_match:
                            m = int(dur_match.group(1) or 0)
                            s = int(dur_match.group(2) or 0)
                            dur_sec = m * 60 + s
                        q = f"{t_artist} - {t_name}" if t_artist else t_name
                        tid = f"am_{idx}"
                        path = f"/api/stream-audio?q={urllib.parse.quote(q)}&id={urllib.parse.quote(tid)}"
                        tracks.append({
                            "id": tid,
                            "title": t_name,
                            "artist": t_artist,
                            "album": title,
                            "duration": dur_sec,
                            "has_art": bool(t_thumb),
                            "artwork": t_thumb,
                            "query": q,
                            "path": path,
                            "isOnlineStream": True,
                            "platform": "Apple Music"
                        })
                    cover = tracks[0]["artwork"] if tracks and tracks[0]["artwork"] else ""
                    return {
                        "platform": "Apple Music",
                        "title": title,
                        "artwork": cover,
                        "tracks": tracks
                    }
            except Exception:
                continue
    except Exception as e:
        print("Apple Music parser error:", e)
    return None

from curl_cffi import requests as cffi_requests

def parse_anghami_url(url: str):
    try:
        s = cffi_requests.Session()
        resp = s.get(url, impersonate="chrome124", allow_redirects=True, timeout=15)
        html = resp.text
        scripts = re.findall(r'<script\b[^>]*>(.*?)</script>', html, re.DOTALL)
        for s in scripts:
            if 'MusicPlaylist' in s or 'MusicAlbum' in s or 'MusicRecording' in s:
                data = json.loads(s.strip())
                if data.get('@type') in ('MusicPlaylist', 'MusicAlbum', 'MusicRecording'):
                    title = data.get('name') or "Anghami Playlist"
                    raw_tracks = data.get('track', [])
                    tracks = []
                    for idx, t in enumerate(raw_tracks):
                        t_name = t.get('name') or 'Unknown Title'
                        by = t.get('byArtist', {})
                        t_artist = by.get('name') if isinstance(by, dict) else str(by)
                        t_image = t.get('image') or ''
                        if 'size=120' in t_image:
                            t_image = t_image.replace('size=120', 'size=600')
                        q = f"{t_artist} - {t_name}" if t_artist else t_name
                        tid = f"ang_{idx}"
                        path = f"/api/stream-audio?q={urllib.parse.quote(q)}&id={urllib.parse.quote(tid)}"
                        tracks.append({
                            "id": tid,
                            "title": t_name,
                            "artist": t_artist,
                            "album": title,
                            "duration": 0,
                            "has_art": bool(t_image),
                            "artwork": t_image,
                            "query": q,
                            "path": path,
                            "isOnlineStream": True,
                            "platform": "Anghami"
                        })
                    return {
                        "platform": "Anghami",
                        "title": title,
                        "artwork": tracks[0]["artwork"] if tracks and tracks[0]["artwork"] else "",
                        "tracks": tracks
                    }
    except Exception as e:
        print("Anghami cffi error:", e)
    return None

def parse_ytdlp_url(url: str):
    if not yt_dlp:
        return None
    ydl_opts = {
        'extract_flat': True,
        'skip_download': True,
        'quiet': True,
        'no_warnings': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return None
            title = info.get('title') or "Online Playlist"
            entries = info.get('entries')
            if entries is None:
                entries = [info]
            tracks = []
            for idx, e in enumerate(entries):
                if not e: continue
                t_title = e.get('title') or 'Unknown Title'
                t_artist = e.get('uploader') or e.get('channel') or ''
                if ' - ' in t_title and not t_artist:
                    parts = t_title.split(' - ', 1)
                    t_artist = parts[0].strip()
                    t_title = parts[1].strip()
                t_duration = int(e.get('duration') or 0)
                t_thumb = e.get('thumbnail') or (e.get('thumbnails', [{}])[-1].get('url') if e.get('thumbnails') else '')
                tid = f"yt_{e.get('id') or idx}"
                q = f"{t_artist} - {t_title}" if t_artist else t_title
                path = f"/api/stream-audio?q={urllib.parse.quote(q)}&id={urllib.parse.quote(tid)}"
                tracks.append({
                    "id": tid,
                    "title": t_title,
                    "artist": t_artist,
                    "album": title,
                    "duration": t_duration,
                    "has_art": bool(t_thumb),
                    "artwork": t_thumb,
                    "query": q,
                    "path": path,
                    "isOnlineStream": True,
                    "platform": "YouTube / Web"
                })
            cover = info.get('thumbnail') or (tracks[0]["artwork"] if tracks and tracks[0]["artwork"] else "")
            return {
                "platform": "YouTube / Web",
                "title": title,
                "artwork": cover,
                "tracks": tracks
            }
    except Exception as e:
        print("yt-dlp parser error:", e)
        return None

def resolve_audio_stream(query: str, track_id: str = ""):
    cache_key = (query.strip(), track_id.strip())
    now = time.time()
    cached = STREAM_CACHE.get(cache_key)
    if cached and (now - cached[1] < 10800): # 3 hour cache
        return cached[0]

    if not yt_dlp:
        return None

    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'noplaylist': True,
    }

    target = query
    if track_id.startswith("yt_") and len(track_id) > 3:
        target = f"https://www.youtube.com/watch?v={track_id[3:]}"
    elif not target.startswith("http"):
        target = f"ytsearch1:{query} audio"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            res = ydl.extract_info(target, download=False)
            entry = res['entries'][0] if 'entries' in res and res['entries'] else res
            stream_url = entry.get('url')
            if stream_url:
                STREAM_CACHE[cache_key] = (stream_url, now)
                return stream_url
    except Exception as e:
        print(f"Error resolving stream for '{query}':", e)
    return None

@app.get("/")
@app.get("/health")
def health():
    return {"status": "ok", "app": "RetroPod Audio Cloud Bridge", "version": "1.0.0"}

@app.post("/api/parse-playlist")
async def api_parse_playlist(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    url = (body.get("url") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="No playlist URL provided")

    res = None
    if "anghami.com" in url:
        res = parse_anghami_url(url)
    elif "spotify.com" in url:
        res = parse_spotify_url(url)
    elif "music.apple.com" in url or "itunes.apple.com" in url:
        res = parse_apple_music_url(url)

    if not res:
        res = parse_ytdlp_url(url)

    if not res or not res.get("tracks"):
        raise HTTPException(status_code=404, detail="Could not extract audio tracks from this URL")

    return {"status": "ok", **res}

@app.get("/api/stream-audio")
async def api_stream_audio(q: str = "", id: str = "", direct: str = "1"):
    if not q and not id:
        raise HTTPException(status_code=400, detail="Missing query or track id")

    stream_url = resolve_audio_stream(q, id)
    if not stream_url:
        raise HTTPException(status_code=404, detail="Audio stream could not be resolved")

    # High-efficiency 302 redirect directly to audio CDN
    return RedirectResponse(url=stream_url, status_code=302)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
