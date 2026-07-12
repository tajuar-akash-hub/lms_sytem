import asyncio
import uuid
from typing import Any

import jwt
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from supabase import Client, create_client

from app.config import get_settings
from app.models import Student
from app.schemas import (
    AuthLoginRequest,
    AuthRefreshRequest,
    AuthSignupRequest,
    AuthTokenResponse,
)

settings = get_settings()
_supabase_client: Client | None = None


def get_supabase_client() -> Client:
    global _supabase_client

    if not settings.supabase_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase authentication is not configured.",
        )

    if _supabase_client is None:
        _supabase_client = create_client(settings.supabase_url, settings.supabase_anon_key)

    return _supabase_client


def _map_supabase_error(error: Exception) -> HTTPException:
    message = str(error)
    lower_message = message.lower()

    if "invalid login credentials" in lower_message or "jwt" in lower_message:
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials.",
        )
    if "already registered" in lower_message or "already exists" in lower_message:
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered.",
        )
    if "password" in lower_message or "validation" in lower_message:
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=message,
        )

    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Supabase authentication request failed.",
    )


def _session_to_response(session: Any, student: Student) -> AuthTokenResponse:
    access_token = getattr(session, "access_token", None)
    refresh_token = getattr(session, "refresh_token", None)

    if not access_token or not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Supabase did not return a session. Disable email confirmation "
                "for local development or confirm the account before login."
            ),
        )

    return AuthTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=getattr(session, "expires_in", None),
        student=student,
    )


async def get_student_by_supabase_id(
    db: AsyncSession, supabase_user_id: uuid.UUID
) -> Student | None:
    result = await db.execute(
        select(Student).where(Student.supabase_user_id == supabase_user_id)
    )
    return result.scalar_one_or_none()


async def get_student_by_email(db: AsyncSession, email: str) -> Student | None:
    result = await db.execute(select(Student).where(Student.email == email))
    return result.scalar_one_or_none()


async def signup_user(
    db: AsyncSession, payload: AuthSignupRequest
) -> AuthTokenResponse:
    client = get_supabase_client()

    try:
        response = await asyncio.to_thread(
            client.auth.sign_up,
            {
                "email": payload.email,
                "password": payload.password,
                "options": {
                    "data": {
                        "name": payload.name,
                        "phone_number": payload.phone_number,
                    }
                },
            },
        )
    except Exception as exc:
        raise _map_supabase_error(exc) from exc

    user = getattr(response, "user", None)
    session = getattr(response, "session", None)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Supabase did not return a user.",
        )

    supabase_user_id = uuid.UUID(str(user.id))
    existing_student = await get_student_by_supabase_id(db, supabase_user_id)
    if existing_student is not None:
        return _session_to_response(session, existing_student)

    existing_email = await get_student_by_email(db, payload.email)
    if existing_email is not None:
        existing_email.supabase_user_id = supabase_user_id
        student = existing_email
    else:
        student = Student(
            supabase_user_id=supabase_user_id,
            name=payload.name,
            email=payload.email,
            phone_number=payload.phone_number,
        )
        db.add(student)

    await db.commit()
    await db.refresh(student)
    return _session_to_response(session, student)


async def login_user(db: AsyncSession, payload: AuthLoginRequest) -> AuthTokenResponse:
    client = get_supabase_client()

    try:
        response = await asyncio.to_thread(
            client.auth.sign_in_with_password,
            {"email": payload.email, "password": payload.password},
        )
    except Exception as exc:
        raise _map_supabase_error(exc) from exc

    user = getattr(response, "user", None)
    session = getattr(response, "session", None)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials.",
        )

    supabase_user_id = uuid.UUID(str(user.id))
    student = await get_student_by_supabase_id(db, supabase_user_id)
    if student is None:
        user_metadata = getattr(user, "user_metadata", None) or {}
        student = await get_student_by_email(db, payload.email)
        if student is None:
            student = Student(
                supabase_user_id=supabase_user_id,
                name=user_metadata.get("name") or payload.email,
                email=payload.email,
            )
            db.add(student)
        else:
            student.supabase_user_id = supabase_user_id

        await db.commit()
        await db.refresh(student)

    return _session_to_response(session, student)


async def refresh_session(payload: AuthRefreshRequest) -> dict[str, Any]:
    client = get_supabase_client()

    try:
        response = await asyncio.to_thread(
            client.auth.refresh_session, payload.refresh_token
        )
    except Exception as exc:
        raise _map_supabase_error(exc) from exc

    session = getattr(response, "session", None)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token.",
        )

    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "token_type": "bearer",
        "expires_in": getattr(session, "expires_in", None),
    }


def verify_access_token(token: str) -> dict[str, Any]:
    if not settings.supabase_jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase JWT verification is not configured.",
        )

    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has expired.",
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token.",
        ) from exc

    if not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token is missing a user id.",
        )

    return payload
