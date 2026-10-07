def resolve_anghami_shortlink(url: str) -> str:
    if "open.anghami.com" in url or "anghami.app.link" in url:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            html = urllib.request.urlopen(req, timeout=8).read().decode('utf-8', errors='replace')
            m = re.search(r'https?://play\.anghami\.com/(playlist|album|song)/\d+', html)
            if m:
                return m.group(0)
        except Exception as e:
            print("Shortlink resolve note:", e)
    return url

def parse_anghami_url(url: str):
    url = resolve_anghami_shortlink(url)
    html = ""
    try:
        from curl_cffi import requests as cffi_requests
        resp = cffi_requests.get(url, impersonate="chrome124", allow_redirects=True, timeout=15)
        html = resp.text
    except Exception as e:
        print("Anghami cffi error:", e)

    if not html:
        return None

    try:
        scripts = re.findall(r'<script\b[^>]*>(.*?)</script>', html, re.DOTALL)
        for s in scripts:
            s = s.strip()
            if '"MusicPlaylist"' in s or '"MusicAlbum"' in s or '"MusicRecording"' in s:
                try:
                    data = json.loads(s)
                    if data.get('@type') in ('MusicPlaylist', 'MusicAlbum', 'MusicRecording'):
                        title = data.get('name') or "Anghami Playlist"
                        raw_tracks = data.get('track', [])
                        if not raw_tracks and data.get('@type') == 'MusicRecording':
                            raw_tracks = [data]
                        tracks = []
                        for idx, t in enumerate(raw_tracks):
                            t_name = t.get('name') or 'Unknown Title'
                            by = t.get('byArtist', {})
                            t_artist = by.get('name') if isinstance(by, dict) else str(by)
                            album_obj = t.get('inAlbum', {})
                            t_album = album_obj.get('name') if isinstance(album_obj, dict) else (title or "Anghami")
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
                                "album": t_album,
                                "duration": 0,
                                "has_art": bool(t_image),
                                "artwork": t_image,
                                "query": q,
                                "path": path,
                                "isOnlineStream": True,
                                "platform": "Anghami"
                            })
                        cover = tracks[0]["artwork"] if tracks and tracks[0]["artwork"] else ""
                        return {
                            "platform": "Anghami",
                            "title": title,
                            "artwork": cover,
                            "tracks": tracks
                        }
                except Exception:
                    continue
    except Exception as e:
        print("Anghami parsing error:", e)

    return None
