# RetroPod Cloud Audio Bridge

This is the lightweight, 24/7 standalone cloud audio bridge for RetroPod. It handles playlist extraction (Anghami, Spotify, Apple Music, YouTube) and direct audio stream resolution so your Android phone never needs a PC or laptop running.

---

## Free 24/7 Deployment Options

### Option 1: Hugging Face Spaces (Recommended - No Credit Card, Never Sleeps)
1. Go to [https://huggingface.co/new-space](https://huggingface.co/new-space)
2. Name your Space: `retropod-bridge`
3. Space SDK: Select **Docker** (Blank)
4. Upload the files from this `cloud_backend` folder (`app.py`, `Dockerfile`, `requirements.txt`).
5. Your Space will build in ~1 minute and give you a permanent HTTPS URL like:
   `https://<your-username>-retropod-bridge.hf.space`
6. Inside the RetroPod app on your phone, paste that URL into the **Cloud Audio Bridge** field and tap **Set**.

---

### Option 2: Render (Free Web Service)
1. Create a free account at [https://render.com](https://render.com)
2. Click **New +** -> **Web Service**
3. Connect your GitHub repository containing this folder (or use Render's Git deploy).
4. Settings:
   - **Environment**: Python
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app:app --host 0.0.0.0 --port $PORT`
   - **Plan**: Free
5. Render will give you a public URL like:
   `https://retropod-bridge.onrender.com`
6. Paste this URL into RetroPod on your phone under **Cloud Audio Bridge**.

---

## Features
- **YouTube Playlists**: Full tracklist extraction and stream audio resolution.
- **Anghami**: Direct album and playlist parsing.
- **Spotify**: Extraction via oEmbed / embed state data.
- **Apple Music**: Schema metadata parsing.
- **CORS Enabled**: Works on Android WebViews, iOS, and Web browsers worldwide.
