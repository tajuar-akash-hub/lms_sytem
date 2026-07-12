from __future__ import annotations

import json
import time
import uuid
from typing import Any

import psycopg2.extras
import yt_dlp

from app.ai.gemini_client import embed_texts, generate_summary
from app.config import get_settings
from app.db_sync import get_sync_conn
from app.services.transcript import (
    chunk_by_time,
    extract_video_id,
    fetch_transcript,
    merge_short_segments,
)


def fetch_video_title(video_id: str) -> str | None:
    try:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(
                f"https://www.youtube.com/watch?v={video_id}",
                download=False,
            )
            return info.get("title") or None
    except Exception as exc:
        print(f"      (could not fetch real title: {exc!r})")
        return None


def _title_has_bangla(title: str) -> bool:
    if not title:
        return False
    return any("\u0980" <= char <= "\u09FF" for char in title)


def detect_preferred_languages(title: str | None) -> list[str]:
    if _title_has_bangla(title or ""):
        return ["bn"]
    return ["en"]


def upsert_video(
    cur,
    source_id: str,
    title: str,
    module_id: uuid.UUID | None = None,
) -> uuid.UUID:
    cur.execute(
        """
        INSERT INTO videos (id, source_id, source_type, title, transcript_status, module_id, updated_at)
        VALUES (%s, %s, 'youtube', %s, 'processing', %s, now())
        ON CONFLICT (source_id) DO UPDATE
          SET title = EXCLUDED.title,
              transcript_status = 'processing',
              module_id = COALESCE(EXCLUDED.module_id, videos.module_id),
              updated_at = now()
        RETURNING id;
        """,
        (str(uuid.uuid4()), source_id, title, str(module_id) if module_id else None),
    )
    return cur.fetchone()[0]


def insert_chunks(
    cur,
    video_id: uuid.UUID,
    chunks: list[dict[str, Any]],
    embeddings: list[list[float]],
) -> int:
    cur.execute("DELETE FROM transcript_chunks WHERE video_id = %s;", (video_id,))
    rows = [
        (
            video_id,
            chunk["text"],
            float(chunk["start_time"]),
            float(chunk["end_time"]),
            int(chunk["chunk_index"]),
            embedding,
        )
        for chunk, embedding in zip(chunks, embeddings)
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


def upsert_summary(cur, video_id: uuid.UUID, summary: dict[str, Any]) -> None:
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


def mark_video_ready(cur, video_id: uuid.UUID) -> None:
    cur.execute(
        "UPDATE videos SET transcript_status = 'ready', updated_at = now() WHERE id = %s;",
        (video_id,),
    )


def mark_video_failed(cur, video_id: uuid.UUID) -> None:
    cur.execute(
        "UPDATE videos SET transcript_status = 'failed', updated_at = now() WHERE id = %s;",
        (video_id,),
    )


def reserve_video(
    url_or_id: str,
    module_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    source_id = extract_video_id(url_or_id)
    title = fetch_video_title(source_id) or f"YouTube {source_id}"
    conn = get_sync_conn()
    try:
        with conn.cursor() as cur:
            video_uuid = upsert_video(cur, source_id, title, module_id=module_id)
        conn.commit()
    finally:
        conn.close()
    return {
        "video_id": str(video_uuid),
        "source_id": source_id,
        "title": title,
        "status": "processing",
    }


def process_video(
    url_or_id: str,
    module_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    source_id = extract_video_id(url_or_id)
    started = time.time()

    print("[1/6] Looking up real video title (to detect language)...")
    real_title = fetch_video_title(source_id)
    title = real_title or f"YouTube {source_id}"
    print(f"      title: {title[:80]}")

    preferred_langs = detect_preferred_languages(title)
    print(f"      language hint: {preferred_langs}")

    print(f"[2/6] Fetching transcript for {source_id}...")
    raw = fetch_transcript(source_id, preferred_languages=preferred_langs)
    merged = merge_short_segments(raw)
    chunks = chunk_by_time(merged, chunk_seconds=settings.video_chunk_seconds)
    print(
        f"      got {len(raw)} raw segments -> {len(merged)} merged -> {len(chunks)} chunks"
    )

    full_transcript_text = " ".join(chunk["text"] for chunk in chunks)

    print(f"[3/6] Embedding {len(chunks)} chunks...")
    embed_started = time.time()
    embeddings = embed_texts([chunk["text"] for chunk in chunks])
    print(
        f"      embedded in {time.time() - embed_started:.1f}s, "
        f"dim={len(embeddings[0]) if embeddings else 0}"
    )

    print("[4/6] Generating summary + questions...")
    summary_started = time.time()
    summary = generate_summary(full_transcript_text, title)
    print(f"      done in {time.time() - summary_started:.1f}s")

    print("[5/6] Writing to database...")
    conn = get_sync_conn()
    conn.autocommit = False
    video_uuid: uuid.UUID | None = None
    try:
        with conn.cursor() as cur:
            video_uuid = upsert_video(cur, source_id, title, module_id=module_id)
            n_chunks = insert_chunks(cur, video_uuid, chunks, embeddings)
            upsert_summary(cur, video_uuid, summary)
            mark_video_ready(cur, video_uuid)
        conn.commit()
    except Exception:
        conn.rollback()
        if video_uuid is not None:
            with conn.cursor() as cur:
                mark_video_failed(cur, video_uuid)
            conn.commit()
        raise
    finally:
        conn.close()

    print(f"[6/6] Done in {time.time() - started:.1f}s total")
    return {
        "video_id": str(video_uuid),
        "source_id": source_id,
        "title": title,
        "n_chunks": n_chunks,
        "summary": summary,
        "status": "ready",
    }
