from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gemini_client import (
    CHAT_SYSTEM_PROMPT,
    call_llm_json,
    call_llm_json_groq,
    embed_query,
)
from app.config import get_settings
from app.db_sync import get_sync_conn


def retrieve_chunks_sync(
    video_uuid: str,
    query_embedding: list[float],
    top_k: int | None = None,
) -> list[dict[str, Any]]:
    settings = get_settings()
    top_k = top_k or settings.top_k_chunks
    conn = get_sync_conn()
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
            "text": row[0],
            "start_time": float(row[1]),
            "end_time": float(row[2]),
            "chunk_index": int(row[3]),
            "distance": float(row[4]),
        }
        for row in rows
    ]


async def retrieve_chunks(
    db: AsyncSession,
    video_uuid: uuid.UUID,
    query_embedding: list[float],
    top_k: int | None = None,
) -> list[dict[str, Any]]:
    settings = get_settings()
    top_k = top_k or settings.top_k_chunks
    result = await db.execute(
        text(
            """
            SELECT chunk_text, start_time, end_time, chunk_index,
                   (embedding <=> :embedding::vector) AS distance
            FROM transcript_chunks
            WHERE video_id = :video_id
            ORDER BY embedding <=> :embedding::vector
            LIMIT :top_k;
            """
        ),
        {
            "embedding": query_embedding,
            "video_id": str(video_uuid),
            "top_k": top_k,
        },
    )
    return [
        {
            "text": row.chunk_text,
            "start_time": float(row.start_time),
            "end_time": float(row.end_time),
            "chunk_index": int(row.chunk_index),
            "distance": float(row.distance),
        }
        for row in result.mappings().all()
    ]


def fetch_recent_history_sync(
    video_uuid: str,
    student_id: str,
    n_turns: int | None = None,
) -> list[dict[str, Any]]:
    settings = get_settings()
    n_turns = n_turns or settings.max_history_turns
    conn = get_sync_conn()
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
    return [
        {"role": row[0], "content": row[1], "cited_timestamp": row[2]}
        for row in reversed(rows)
    ]


async def fetch_recent_history(
    db: AsyncSession,
    video_uuid: uuid.UUID,
    student_id: uuid.UUID,
    n_turns: int | None = None,
) -> list[dict[str, Any]]:
    settings = get_settings()
    n_turns = n_turns or settings.max_history_turns
    result = await db.execute(
        text(
            """
            SELECT role, content, cited_timestamp, created_at
            FROM chat_messages
            WHERE video_id = :video_id AND student_id = :student_id
            ORDER BY created_at DESC
            LIMIT :limit;
            """
        ),
        {
            "video_id": str(video_uuid),
            "student_id": str(student_id),
            "limit": n_turns * 2,
        },
    )
    rows = result.mappings().all()
    return [
        {
            "role": row.role,
            "content": row.content,
            "cited_timestamp": row.cited_timestamp,
        }
        for row in reversed(rows)
    ]


def answer_question(
    video_uuid: str,
    source_id: str,
    question: str,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    query_embedding = embed_query(question)
    chunks = retrieve_chunks_sync(video_uuid, query_embedding)
    if not chunks:
        return {
            "answer": (
                "This video has no transcript available yet, so I cannot "
                "answer questions about it."
            ),
            "cited_timestamp": None,
            "cited_text": None,
        }

    context_lines = []
    for chunk in chunks:
        minutes = int(chunk["start_time"] // 60)
        seconds = int(chunk["start_time"] % 60)
        context_lines.append(f"[{minutes}:{seconds:02d}] {chunk['text']}")
    context = "\n".join(context_lines)

    history_block = ""
    if history:
        history_lines = ["Previous conversation in this lesson (oldest first):"]
        for turn in history:
            prefix = "Student" if turn["role"] == "user" else "Tutor"
            history_lines.append(f"{prefix}: {turn['content']}")
        history_block = "\n".join(history_lines) + "\n\n"
    else:
        history_block = (
            "Previous conversation in this lesson: "
            "(none yet — this is the first turn)\n\n"
        )

    user_prompt = (
        f"YouTube video ID: {source_id}\n\n"
        f"Transcript excerpts (with timestamps):\n\n{context}\n\n"
        f"{history_block}"
        f"Student question: {question}"
    )

    data = call_llm_json(CHAT_SYSTEM_PROMPT, user_prompt, temperature=0.2)
    if data == "QUOTA":
        data = call_llm_json_groq(CHAT_SYSTEM_PROMPT, user_prompt, temperature=0.2)

    if not data:
        return {
            "answer": (
                "I'm having trouble reaching the AI service right now. "
                "Please try again in a moment."
            ),
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
    if cited_ts is not None and chunks:
        nearest = min(chunks, key=lambda chunk: abs(chunk["start_time"] - cited_ts))
        if abs(nearest["start_time"] - cited_ts) <= 30.0:
            cited_text = nearest["text"]
        else:
            cited_ts = chunks[0]["start_time"]
            cited_text = chunks[0]["text"]
    elif chunks:
        cited_ts = chunks[0]["start_time"]
        cited_text = chunks[0]["text"]

    return {
        "answer": data.get("answer", "").strip(),
        "cited_timestamp": cited_ts,
        "cited_text": cited_text,
    }
