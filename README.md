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