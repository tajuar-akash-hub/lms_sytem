# Chat with the Video

A hackathon MVP that lets students ask questions about a YouTube video and get
answers grounded in that video's transcript — with timestamps that jump the
player to the relevant part.

## Stack
- **Backend:** FastAPI + Python 3.12
- **Database:** Postgres + pgvector (Neon free tier)
- **LLM:** Gemini (primary) + Groq Llama 3.3 70B (fallback)
- **Embeddings:** Gemini `text-embedding-001` (768-dim)
- **Transcription:** `youtube-transcript-api` → Groq Whisper (fallback) → Gemini ASR (last resort)
- **Frontend:** Single-file `static/index.html` (Tailwind via CDN, no build step)

## Local setup
```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in your keys
python init_db.py      # creates tables
python app.py          # runs on http://localhost:8000
```

## Deploy on Render
See `DEPLOY.md` for step-by-step instructions.

## Keep-alive (Render free tier)
Render's free tier spins the web service down after ~15 minutes of no traffic,
so the first request after idle hits a cold start (~30s). To keep the demo
always responsive, this repo includes `.github/workflows/keep-alive.yml`,
which pings `/internal/health` every 10 minutes from GitHub Actions.

One-time setup:
1. GitHub repo -> **Settings -> Secrets and variables -> Actions**.
2. Add a repository secret named `RENDER_URL` with your Render service URL
   (e.g. `https://chat-with-video.onrender.com` — no trailing slash).
3. Push the workflow file. The Actions tab will start showing the runs on
   schedule. You can also trigger it manually with `workflow_dispatch`.

Notes:
- Uses your Render monthly "always-on" hours (750 hr/mo free).
- Cold starts can still briefly 503 — the workflow does not fail the build.