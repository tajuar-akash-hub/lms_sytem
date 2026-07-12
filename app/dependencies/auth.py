import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Student
from app.services.auth import get_student_by_supabase_id, verify_access_token

security = HTTPBearer()


async def get_current_student(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Student:
    payload = verify_access_token(credentials.credentials)
    student = await get_student_by_supabase_id(db, uuid.UUID(payload["sub"]))

    if student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student profile not found.",
        )

    return student
