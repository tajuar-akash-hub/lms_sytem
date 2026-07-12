from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_student
from app.models import Student
from app.schemas import (
    AuthLoginRequest,
    AuthMessageResponse,
    AuthRefreshRequest,
    AuthSignupRequest,
    AuthTokenResponse,
    StudentRead,
)
from app.services.auth import login_user, refresh_session, signup_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/signup",
    response_model=AuthTokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def signup(
    payload: AuthSignupRequest,
    db: AsyncSession = Depends(get_db),
):
    return await signup_user(db, payload)


@router.post("/login", response_model=AuthTokenResponse)
async def login(
    payload: AuthLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    return await login_user(db, payload)


@router.post("/refresh")
async def refresh(payload: AuthRefreshRequest):
    return await refresh_session(payload)


@router.get("/me", response_model=StudentRead)
async def me(current_student: Student = Depends(get_current_student)):
    return current_student


@router.post("/logout", response_model=AuthMessageResponse)
async def logout(current_student: Student = Depends(get_current_student)):
    return {"message": "Logged out. Discard the access and refresh tokens client-side."}
