"""FastAPI backend for the chat-with-video feature.

Endpoints:
  GET  /                       -> serves the frontend (index.html)
  GET  /api/videos             -> list all processed videos
  GET  /api/videos/{id}        -> get one video + summary + suggested questions
  POST /api/videos             -> process a new video (manual trigger)
  POST /api/videos/{id}/chat   -> ask a question, get grounded answer + timestamp
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import List, Optional

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from google import genai
from pydantic import BaseModel, Field

load_dotenv(Path(__file__).parent / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEN_MODEL = "gemini-2.5-flash"
EMBED_MODEL = "gemini-embedding-001"
EMBED_DIM = 768
TOP_K_CHUNKS = 5
MAX_HISTORY_TURNS = 3  # how many prior Q&A pairs to include in the prompt for memory

if not DATABASE_URL or not GEMINI_API_KEY:
    raise SystemExit("DATABASE_URL and GEMINI_API_KEY must be set in .env")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class ProcessVideoRequest(BaseModel):
    url_or_id: str = Field(..., description="YouTube URL or 11-char video ID")


class PlaylistPollRequest(BaseModel):
    playlist_id: str = Field(..., description="YouTube playlist ID (the part after list=)")
    dry_run: bool = Field(default=False, description="If true, just report what would be processed")


class LMSWebhookPayload(BaseModel):
    """Payload from the LMS when a new video is uploaded."""
    video_url: str = Field(..., description="URL or ID of the video to process")
    source_type: str = Field(default="youtube", description="Source platform (youtube, s3, etc.)")
    title: Optional[str] = None
    metadata: Optional[dict] = None


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    student_id: Optional[str] = None  # if absent, a session UUID is used


class ChatResponse(BaseModel):
    answer: str
    cited_timestamp: Optional[float] = None
    cited_text: Optional[str] = None
    message_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_conn():
    return psycopg2.connect(DATABASE_URL)


def get_genai():
    return genai.Client(api_key=GEMINI_API_KEY)


def video_to_dict(row, summary_row=None) -> dict:
    """Convert a DB row tuple to a JSON-friendly dict."""
    vid_id, source_id, source_type, title, status, *_ = row
    out = {
        "id": str(vid_id),
        "source_id": source_id,
        "source_type": source_type,
        "title": title,
        "transcript_status": status,
    }
    if summary_row:
        _, _, overview, key_concepts, suggested_questions = summary_row
        out["summary"] = {
            "overview": overview,
            "key_concepts": key_concepts if isinstance(key_concepts, list)
                else json.loads(key_concepts or "[]"),
            "suggested_questions": suggested_questions if isinstance(suggested_questions, list)
                else json.loads(suggested_questions or "[]"),
        }
    return out


def embed_query(text: str) -> List[float]:
    client = get_genai()
    resp = client.models.embed_content(
        model=EMBED_MODEL,
        contents=[text],
        config={"output_dimensionality": EMBED_DIM},
    )
    return resp.embeddings[0].values


def retrieve_chunks(video_uuid: str, query_embedding: List[float], top_k: int = TOP_K_CHUNKS) -> List[dict]:
    """Return the top_k most similar chunks for a video using cosine distance."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT chunk_text, start_time, end_time, chunk_index,
               (embedding <=> %s::vector) AS distance
        FROM transcript_chunks
        WHERE video_id = %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s;
        """,
        (query_embedding, video_uuid, query_embedding, top_k),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {
            "text": r[0],
            "start_time": float(r[1]),
            "end_time": float(r[2]),
            "chunk_index": int(r[3]),
            "distance": float(r[4]),
        }
        for r in rows
    ]


def fetch_recent_history(video_uuid: str, student_id: str, n_turns: int = MAX_HISTORY_TURNS) -> List[dict]:
    """Return the last n_turns user/assistant exchanges for this student+video, oldest first.

    Uses the chat_messages_video_student_idx index for fast lookup.
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT role, content, cited_timestamp, created_at
        FROM chat_messages
        WHERE video_id = %s AND student_id = %s
        ORDER BY created_at DESC
        LIMIT %s;
        """,
        (video_uuid, student_id, n_turns * 2),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    # rows come newest-first; reverse to chronological order for the prompt
    return [
        {"role": r[0], "content": r[1], "cited_timestamp": r[2]}
        for r in reversed(rows)
    ]


CHAT_SYSTEM_PROMPT = """You are a tutor for a Bangla machine-learning course.
The student is watching a specific video and has asked a question about it.

You will receive 3-5 short transcript excerpts from that exact video. Each excerpt
has a start time (seconds) that shows where in the video it came from.

Rules:
1. Answer ONLY using information from the provided excerpts.
2. If the answer is not in the excerpts, say plainly that the video does not
   cover this topic. Do NOT guess or use outside knowledge.
3. Be concise (2-4 sentences). Use English unless the user wrote in another language.
4. When you use information from a specific excerpt, mention the timestamp
   inline like "(at 4:23 in the video)".
5. Do not repeat the question.
6. You may also see the recent conversation history for this lesson. Use it
   only to resolve references like "that", "it", "this concept", or
   follow-up questions. Every factual claim must still be grounded in the
   transcript excerpts above.

Output a single JSON object with keys:
  - answer: your response to the student (string)
  - cited_timestamp: the single best start_time (float, seconds) of the excerpt
                     that most directly supports your answer, or null if you
                     are saying the video doesn't cover it
"""


def _call_llm_json(system_prompt: str, user_prompt: str, temperature: float = 0.2) -> Optional[dict]:
    """Call Gemini (with model fallback) to get a JSON dict back.

    Returns None if all attempts fail. On quota errors, returns "QUOTA"
    sentinel so the caller can switch providers if available.
    """
    client = get_genai()
    for model_name in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest"]:
        for attempt in range(2):
            try:
                resp = client.models.generate_content(
                    model=model_name,
                    contents=user_prompt,
                    config={
                        "system_instruction": system_prompt,
                        "response_mime_type": "application/json",
                        "temperature": temperature,
                    },
                )
                raw = resp.text or "{}"
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    cleaned = raw.strip().strip("`")
                    if cleaned.startswith("json"):
                        cleaned = cleaned[4:]
                    return json.loads(cleaned)
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                    # No point retrying — quota exhausted
                    return "QUOTA"
                time.sleep(2 ** attempt)
    return None


def _call_llm_json_groq(system_prompt: str, user_prompt: str, temperature: float = 0.2) -> Optional[dict]:
    """Fallback: use Groq's hosted Llama model for JSON-mode generation."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt + "\n\nRespond ONLY with valid JSON."},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        print(f"Groq LLM fallback failed: {e!r}")
        return None


def answer_question(video_uuid: str, source_id: str, question: str, history: Optional[List[dict]] = None) -> dict:
    """RAG: retrieve chunks, ask the LLM, return grounded answer with timestamp.

    If `history` is provided (oldest-first list of prior turns with
    role/content/cited_timestamp), it is injected into the prompt so the
    model can resolve follow-up references like "it" or "that".
    """
    q_emb = embed_query(question)
    chunks = retrieve_chunks(video_uuid, q_emb, top_k=TOP_K_CHUNKS)
    if not chunks:
        return {
            "answer": "This video has no transcript available yet, so I cannot answer questions about it.",
            "cited_timestamp": None,
            "cited_text": None,
        }

    context_lines = []
    for c in chunks:
        mm = int(c["start_time"] // 60)
        ss = int(c["start_time"] % 60)
        context_lines.append(f"[{mm}:{ss:02d}] {c['text']}")
    context = "\n".join(context_lines)

    # Build conversation-history block (oldest first) if any
    history_block = ""
    if history:
        history_lines = ["Previous conversation in this lesson (oldest first):"]
        for turn in history:
            prefix = "Student" if turn["role"] == "user" else "Tutor"
            history_lines.append(f"{prefix}: {turn['content']}")
        history_block = "\n".join(history_lines) + "\n\n"

    user_prompt = (
        f"YouTube video ID: {source_id}\n\n"
        f"Transcript excerpts (with timestamps):\n\n{context}\n\n"
        f"{history_block}"
        f"Student question: {question}"
    )

    # Try Gemini first
    data = _call_llm_json(CHAT_SYSTEM_PROMPT, user_prompt, temperature=0.2)

    # If Gemini is quota-limited, fall back to Groq
    if data == "QUOTA":
        print("      Gemini quota hit, falling back to Groq for chat")
        data = _call_llm_json_groq(CHAT_SYSTEM_PROMPT, user_prompt, temperature=0.2)

    if not data:
        return {
            "answer": "I'm having trouble reaching the AI service right now. Please try again in a moment.",
            "cited_timestamp": None,
            "cited_text": None,
        }

    cited_ts = data.get("cited_timestamp")
    if cited_ts is not None:
        try:
            cited_ts = float(cited_ts)
        except (TypeError, ValueError):
            cited_ts = None

    cited_text = None
    if cited_ts is not None:
        best = min(chunks, key=lambda c: abs(c["start_time"] - cited_ts))
        cited_text = best["text"]

    return {
        "answer": data.get("answer", "").strip(),
        "cited_timestamp": cited_ts,
        "cited_text": cited_text,
    }


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="Chat with the Video", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).parent / "static"


@app.get("/")
def serve_index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/videos")
def list_videos():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT v.id, v.source_id, v.source_type, v.title, v.transcript_status,
               s.id, s.overview, s.key_concepts, s.suggested_questions
        FROM videos v
        LEFT JOIN video_summaries s ON s.video_id = v.id
        WHERE v.transcript_status = 'ready'
        ORDER BY v.created_at DESC;
        """
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    out = []
    for r in rows:
        v_part = video_to_dict(r[:5])
        s_part = r[5:]
        if s_part[0]:
            v_part["summary"] = {
                "overview": s_part[1],
                "key_concepts": s_part[2] if isinstance(s_part[2], list) else json.loads(s_part[2] or "[]"),
                "suggested_questions": s_part[3] if isinstance(s_part[3], list) else json.loads(s_part[3] or "[]"),
            }
        out.append(v_part)
    return out


@app.get("/api/videos/{video_id}")
def get_video(video_id: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT v.id, v.source_id, v.source_type, v.title, v.transcript_status,
               s.id, s.overview, s.key_concepts, s.suggested_questions
        FROM videos v
        LEFT JOIN video_summaries s ON s.video_id = v.id
        WHERE v.source_id = %s
           OR (v.id::text = %s AND %s ~* '^[0-9a-f-]{36}$')
        LIMIT 1;
        """,
        (video_id, video_id, video_id),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Video not found")
    v_part = video_to_dict(row[:5])
    s_part = row[5:]
    if s_part[0]:
        v_part["summary"] = {
            "overview": s_part[1],
            "key_concepts": s_part[2] if isinstance(s_part[2], list) else json.loads(s_part[2] or "[]"),
            "suggested_questions": s_part[3] if isinstance(s_part[3], list) else json.loads(s_part[3] or "[]"),
        }
    return v_part


@app.post("/api/videos")
def process_video(req: ProcessVideoRequest):
    # Import here to avoid pulling heavy deps at module import time
    from pipeline import process_video

    try:
        result = process_video(req.url_or_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {e!s}")

    return {
        "video_id": result["video_id"],
        "source_id": result["source_id"],
        "n_chunks": result["n_chunks"],
        "summary": result["summary"],
    }


@app.post("/internal/check-playlist")
def check_playlist(req: PlaylistPollRequest):
    """Poll a YouTube playlist and process any new videos not yet in the DB.

    Designed to be called by a Render Cron Job on a schedule (e.g., every
    15 minutes). Returns a summary of what was processed.
    """
    from auto_process import check_playlist_for_new_videos

    try:
        result = check_playlist_for_new_videos(req.playlist_id, dry_run=req.dry_run)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Playlist check failed: {e!s}")

    return result


@app.post("/webhook/video-uploaded")
def lms_video_uploaded(payload: LMSWebhookPayload):
    """Webhook endpoint for the LMS to call when a new video is uploaded.

    In production, the LMS will POST this with the video's URL/ID and we'll
    run the pipeline to make it chat-ready. For YouTube videos we use the
    same audio-transcription path. For LMS-hosted videos, the URL can point
    to an S3/R2 object we'll download and transcribe.
    """
    from auto_process import process_lms_webhook

    try:
        result = process_lms_webhook(
            video_url_or_id=payload.video_url,
            source_type=payload.source_type,
            title=payload.title,
            metadata=payload.metadata,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Webhook processing failed: {e!s}")

    return result


@app.get("/internal/health")
def health():
    """Lightweight health check — also confirms DB connectivity."""
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM videos;")
        n = cur.fetchone()[0]
        cur.close()
        conn.close()
        return {"status": "ok", "video_count": n}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"DB unavailable: {e!s}")


@app.post("/api/videos/{video_id}/chat")
def chat(video_id: str, req: ChatRequest):
    # Look up the video (accept either source_id or UUID)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, source_id FROM videos
        WHERE source_id = %s
           OR (id::text = %s AND %s ~* '^[0-9a-f-]{36}$')
        LIMIT 1;
        """,
        (video_id, video_id, video_id),
    )
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close()
        raise HTTPException(status_code=404, detail="Video not found")
    real_uuid, source_id = row

    student_id = req.student_id or str(uuid.uuid4())
    message_id = str(uuid.uuid4())

    # Load prior conversation history BEFORE saving the new user message
    # so the new turn doesn't appear at the top of the history block.
    history = fetch_recent_history(real_uuid, student_id, n_turns=MAX_HISTORY_TURNS)

    # Save the user's message
    cur.execute(
        """
        INSERT INTO chat_messages (id, student_id, video_id, role, content)
        VALUES (%s, %s, %s, 'user', %s);
        """,
        (message_id, student_id, real_uuid, req.question),
    )
    conn.commit()
    cur.close()
    conn.close()

    result = answer_question(real_uuid, source_id, req.question, history=history)

    # Save the assistant's reply
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO chat_messages (id, student_id, video_id, role, content, cited_timestamp)
        VALUES (%s, %s, %s, 'assistant', %s, %s);
        """,
        (str(uuid.uuid4()), student_id, real_uuid, result["answer"], result["cited_timestamp"]),
    )
    conn.commit()
    cur.close()
    conn.close()

    return ChatResponse(
        answer=result["answer"],
        cited_timestamp=result["cited_timestamp"],
        cited_text=result["cited_text"],
        message_id=message_id,
    )


# Static files (CSS/JS) served from /static/*
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))