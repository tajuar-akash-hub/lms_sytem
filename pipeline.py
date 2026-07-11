"""End-to-end ingestion pipeline for a single YouTube video.

Steps:
  1. Fetch the transcript
  2. Chunk into ~60s segments
  3. Embed each chunk with Gemini (gemini-embedding-001, 768-dim)
  4. Insert video row, transcript_chunks rows
  5. Generate summary + key concepts + suggested questions with Gemini
  6. Insert into video_summaries

Run:
  python pipeline.py <youtube_url_or_id>
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import List

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from google import genai

from transcript_fetcher import (
    fetch_transcript,
    merge_short_segments,
    chunk_by_time,
    extract_video_id,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
load_dotenv(Path(__file__).parent / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
EMBED_MODEL = "gemini-embedding-001"
EMBED_DIM = 768
GEN_MODEL = "gemini-2.5-flash"  # fast + cheap; good enough for summaries
CHUNK_SECONDS = 60.0

if not GEMINI_API_KEY or not DATABASE_URL:
    raise SystemExit("GEMINI_API_KEY and DATABASE_URL must be set in .env")


# ---------------------------------------------------------------------------
# Gemini helpers
# ---------------------------------------------------------------------------
def get_client() -> genai.Client:
    return genai.Client(api_key=GEMINI_API_KEY)


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Embed a batch of texts. Gemini supports batches natively.

    On any per-item failure, we fall back to embedding one-by-one so the
    whole run doesn't fail because of one bad chunk.
    """
    client = get_client()
    try:
        resp = client.models.embed_content(
            model=EMBED_MODEL,
            contents=texts,
            config={"output_dimensionality": EMBED_DIM},
        )
        return [e.values for e in resp.embeddings]
    except Exception:
        # Per-item fallback
        out = []
        for t in texts:
            r = client.models.embed_content(
                model=EMBED_MODEL,
                contents=[t],
                config={"output_dimensionality": EMBED_DIM},
            )
            out.append(r.embeddings[0].values)
        return out


SUMMARY_SYSTEM_PROMPT = """You are a teaching assistant for a Bangla machine-learning course.
Given a video transcript (which may be auto-generated and noisy), produce a JSON object with:
  - overview: 2-4 sentence summary of what the video teaches (in English, simple)
  - key_concepts: array of 3-7 short concept names mentioned in the video (e.g. ["linear regression", "cost function"])
  - suggested_questions: array of exactly 5 short student questions a learner might ask about THIS video's content (1 sentence each)

Rules:
- Output ONLY valid JSON, no markdown fences, no preamble.
- Questions must be answerable from the transcript itself.
- Concepts should match terminology the video actually uses.
"""


def generate_summary(transcript_text: str, title: str) -> dict:
    """Ask Gemini for a summary + key concepts + 5 suggested questions.

    Retries with backoff on transient 5xx errors. Falls back to
    gemini-2.0-flash if 2.5-flash is unavailable.
    """
    client = get_client()
    user_prompt = (
        f"VIDEO TITLE: {title}\n\n"
        f"TRANSCRIPT (may contain auto-caption noise):\n\n{transcript_text}\n\n"
        "Return JSON with keys: overview, key_concepts, suggested_questions."
    )

    models_to_try = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest"]
    last_err: Optional[Exception] = None
    for model_name in models_to_try:
        for attempt in range(3):
            try:
                resp = client.models.generate_content(
                    model=model_name,
                    contents=user_prompt,
                    config={
                        "system_instruction": SUMMARY_SYSTEM_PROMPT,
                        "response_mime_type": "application/json",
                        "temperature": 0.3,
                    },
                )
                raw = resp.text or "{}"
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    cleaned = raw.strip().strip("`")
                    if cleaned.startswith("json"):
                        cleaned = cleaned[4:]
                    data = json.loads(cleaned)
                data.setdefault("overview", "")
                data.setdefault("key_concepts", [])
                data.setdefault("suggested_questions", [])
                if model_name != GEN_MODEL:
                    print(f"      (summary used fallback model {model_name})")
                return data
            except Exception as e:
                last_err = e
                wait = 2 ** attempt
                print(f"      summary attempt {attempt+1} with {model_name} failed: {type(e).__name__}, retrying in {wait}s...")
                time.sleep(wait)
    raise RuntimeError(f"All summary attempts failed: {last_err!r}")


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def get_conn():
    return psycopg2.connect(DATABASE_URL)


def fetch_video_title(video_id: str) -> Optional[str]:
    """Fetch the real YouTube video title via yt-dlp --dump-json (no download)."""
    try:
        import yt_dlp
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(
                f"https://www.youtube.com/watch?v={video_id}", download=False
            )
            return info.get("title") or None
    except Exception as e:
        print(f"      (could not fetch real title: {e!r})")
        return None


def upsert_video(cur, source_id: str, title: str) -> str:
    """Insert video if new, otherwise fetch its id. Returns the video id."""
    cur.execute(
        """
        INSERT INTO videos (source_id, source_type, title, transcript_status, updated_at)
        VALUES (%s, 'youtube', %s, 'processing', now())
        ON CONFLICT (source_id) DO UPDATE
          SET title = EXCLUDED.title,
              transcript_status = 'processing',
              updated_at = now()
        RETURNING id;
        """,
        (source_id, title),
    )
    return cur.fetchone()[0]


def insert_chunks(cur, video_id: str, chunks: List[dict], embeddings: List[List[float]]) -> int:
    """Replace all chunks for this video with the new set, then insert fresh ones."""
    cur.execute("DELETE FROM transcript_chunks WHERE video_id = %s;", (video_id,))
    rows = [
        (
            video_id,
            c["text"],
            float(c["start_time"]),
            float(c["end_time"]),
            int(c["chunk_index"]),
            emb,
        )
        for c, emb in zip(chunks, embeddings)
    ]
    psycopg2.extras.execute_values(
        cur,
        """
        INSERT INTO transcript_chunks
          (video_id, chunk_text, start_time, end_time, chunk_index, embedding)
        VALUES %s;
        """,
        rows,
    )
    return len(rows)


def upsert_summary(cur, video_id: str, summary: dict) -> None:
    cur.execute("DELETE FROM video_summaries WHERE video_id = %s;", (video_id,))
    cur.execute(
        """
        INSERT INTO video_summaries (video_id, overview, key_concepts, suggested_questions, updated_at)
        VALUES (%s, %s, %s::jsonb, %s::jsonb, now());
        """,
        (
            video_id,
            summary.get("overview", ""),
            json.dumps(summary.get("key_concepts", [])),
            json.dumps(summary.get("suggested_questions", [])),
        ),
    )


def mark_video_ready(cur, video_id: str) -> None:
    cur.execute(
        "UPDATE videos SET transcript_status = 'ready', updated_at = now() WHERE id = %s;",
        (video_id,),
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def process_video(url_or_id: str) -> dict:
    """Full pipeline. Returns a summary dict for logging."""
    video_id = extract_video_id(url_or_id)
    t0 = time.time()

    print(f"[1/5] Fetching transcript for {video_id}...")
    raw = fetch_transcript(video_id, preferred_languages=["bn", "en"])
    merged = merge_short_segments(raw)
    chunks = chunk_by_time(merged, chunk_seconds=CHUNK_SECONDS)
    print(f"      got {len(raw)} raw segments -> {len(merged)} merged -> {len(chunks)} chunks")

    print(f"[2/6] Looking up real video title...")
    real_title = fetch_video_title(video_id)
    title = real_title or f"YouTube {video_id}"
    print(f"      title: {title[:80]}")
    full_transcript_text = " ".join(c["text"] for c in chunks)

    print(f"[3/6] Embedding {len(chunks)} chunks...")
    t1 = time.time()
    embeddings = embed_texts([c["text"] for c in chunks])
    print(f"      embedded in {time.time()-t1:.1f}s, dim={len(embeddings[0])}")

    print(f"[4/6] Generating summary + questions...")
    t1 = time.time()
    summary = generate_summary(full_transcript_text, title)
    print(f"      done in {time.time()-t1:.1f}s")
    print(f"      overview: {summary.get('overview','')[:120]}...")
    print(f"      concepts: {summary.get('key_concepts', [])}")
    print(f"      sample Q: {summary.get('suggested_questions', ['(none)'])[0] if summary.get('suggested_questions') else '(none)'}")

    print(f"[5/6] Writing to database...")
    conn = get_conn()
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            vid_uuid = upsert_video(cur, video_id, title)
            n_chunks = insert_chunks(cur, vid_uuid, chunks, embeddings)
            upsert_summary(cur, vid_uuid, summary)
            mark_video_ready(cur, vid_uuid)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    print(f"      wrote video {vid_uuid} with {n_chunks} chunks + summary")

    print(f"[6/6] Done in {time.time()-t0:.1f}s total")
    return {
        "video_id": vid_uuid,
        "source_id": video_id,
        "title": title,
        "n_chunks": n_chunks,
        "summary": summary,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pipeline.py <youtube_url_or_id>")
        sys.exit(1)
    result = process_video(sys.argv[1])
    print("\n=== RESULT ===")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))