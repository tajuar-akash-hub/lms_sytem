from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.rag import answer_question, fetch_recent_history
from app.config import get_settings
from app.database import get_db
from app.dependencies.auth import get_current_student
from app.models import ChatMessage, Video
from app.schemas.videos import (
    ChatRequest,
    ChatResponse,
    LMSWebhookPayload,
    PlaylistPollRequest,
    ProcessVideoRequest,
    ProcessVideoResponse,
    VideoRead,
    VideoSummaryRead,
)
from app.services.auto_process import check_playlist_for_new_videos, process_lms_webhook
from app.services.video_pipeline import process_video, reserve_video
from app.tasks.background import process_video_task

router = APIRouter(tags=["videos"])
optional_bearer = HTTPBearer(auto_error=False)


def _parse_json_field(value: Any) -> list[str]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return json.loads(value or "[]")
    return []


def _video_to_read(video: Video) -> VideoRead:
    summary = None
    if video.summary is not None:
        summary = VideoSummaryRead(
            overview=video.summary.overview,
            key_concepts=_parse_json_field(video.summary.key_concepts),
            suggested_questions=_parse_json_field(video.summary.suggested_questions),
        )
    return VideoRead(
        id=str(video.id),
        source_id=video.source_id,
        source_type=video.source_type,
        title=video.title,
        transcript_status=video.transcript_status,
        summary=summary,
    )


async def _get_video_by_identifier(
    db: AsyncSession,
    video_id: str,
) -> Video | None:
    filters = [Video.source_id == video_id]
    if _is_uuid(video_id):
        filters.append(Video.id == uuid.UUID(video_id))
    stmt = (
        select(Video)
        .options(selectinload(Video.summary))
        .where(or_(*filters))
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def _run_process_video(url_or_id: str, module_id: str | None) -> None:
    parsed_module_id = uuid.UUID(module_id) if module_id and _is_uuid(module_id) else None
    process_video(url_or_id, module_id=parsed_module_id)


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def _coerce_student_id(value: str | None) -> uuid.UUID:
    if not value:
        return uuid.uuid4()
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return uuid.uuid5(uuid.NAMESPACE_DNS, f"lms-chat:{value}")


async def _resolve_student_id(
    db: AsyncSession,
    credentials: HTTPAuthorizationCredentials | None,
    requested_student_id: str | None,
) -> uuid.UUID:
    if credentials is not None:
        student = await get_current_student(credentials, db)
        return student.id
    return _coerce_student_id(requested_student_id)


@router.get("/api/videos", response_model=list[VideoRead])
async def list_videos(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Video)
        .options(selectinload(Video.summary))
        .where(Video.transcript_status == "ready")
        .order_by(Video.created_at.desc())
    )
    videos = result.scalars().all()
    return [_video_to_read(video) for video in videos]


@router.get("/api/videos/{video_id}", response_model=VideoRead)
async def get_video(video_id: str, db: AsyncSession = Depends(get_db)):
    video = await _get_video_by_identifier(db, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    return _video_to_read(video)


@router.post("/api/videos", response_model=ProcessVideoResponse)
async def process_video_endpoint(
    req: ProcessVideoRequest,
    background_tasks: BackgroundTasks,
):
    settings = get_settings()
    if not settings.ai_configured:
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY is not configured")

    module_id = uuid.UUID(req.module_id) if req.module_id and _is_uuid(req.module_id) else None
    reserved = reserve_video(req.url_or_id, module_id=module_id)
    try:
        process_video_task.delay(req.url_or_id, req.module_id)
    except Exception:
        background_tasks.add_task(_run_process_video, req.url_or_id, req.module_id)
    return ProcessVideoResponse(
        video_id=reserved["video_id"],
        source_id=reserved["source_id"],
        status="processing",
    )


@router.post("/internal/check-playlist")
async def check_playlist(req: PlaylistPollRequest):
    try:
        return check_playlist_for_new_videos(req.playlist_id, dry_run=req.dry_run)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Playlist check failed: {exc!s}") from exc


@router.post("/webhook/video-uploaded")
async def lms_video_uploaded(payload: LMSWebhookPayload):
    try:
        return process_lms_webhook(
            video_url_or_id=payload.video_url,
            source_type=payload.source_type,
            title=payload.title,
            metadata=payload.metadata,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Webhook processing failed: {exc!s}"
        ) from exc


@router.get("/internal/health")
async def internal_health(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("SELECT count(*) AS video_count FROM videos"))
    row = result.mappings().one()
    return {"status": "ok", "video_count": row["video_count"]}


@router.post("/api/videos/{video_id}/chat", response_model=ChatResponse)
async def chat(
    video_id: str,
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(optional_bearer)
    ] = None,
):
    video = await _get_video_by_identifier(db, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    student_id = await _resolve_student_id(db, credentials, req.student_id)
    message_id = uuid.uuid4()
    history = await fetch_recent_history(db, video.id, student_id)

    user_message = ChatMessage(
        id=message_id,
        student_id=student_id,
        video_id=video.id,
        role="user",
        content=req.question,
    )
    db.add(user_message)
    await db.commit()

    result = answer_question(str(video.id), video.source_id, req.question, history=history)

    assistant_message = ChatMessage(
        id=uuid.uuid4(),
        student_id=student_id,
        video_id=video.id,
        role="assistant",
        content=result["answer"],
        cited_timestamp=result["cited_timestamp"],
    )
    db.add(assistant_message)
    await db.commit()

    return ChatResponse(
        answer=result["answer"],
        cited_timestamp=result["cited_timestamp"],
        cited_text=result["cited_text"],
        message_id=str(message_id),
    )
