from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.routers.auth import router as auth_router

settings = get_settings()

app = FastAPI(
    title="Phitron EdTech API",
    description="AI-driven EdTech platform backend",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/health/db")
async def database_health_check(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("SELECT 1 AS connected"))
    row = result.mappings().one()
    return {"status": "ok", "database": row["connected"]}
