import ssl
from functools import lru_cache
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import certifi
from pydantic_settings import BaseSettings, SettingsConfigDict

ASYNC_QUERY_BLOCKLIST = {"channel_binding", "sslmode"}


def _normalize_postgres_url(url: str, driver: str, blocklist: set[str] | None = None) -> str:
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", f"postgresql+{driver}://", 1)

    parsed = urlparse(url)
    blocked = blocklist or set()
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key not in blocked
    ]
    return urlunparse(parsed._replace(query=urlencode(query)))


def _ssl_connect_args(url: str) -> dict:
    parsed = urlparse(url.replace("postgres://", "postgresql://", 1))
    sslmode = dict(parse_qsl(parsed.query)).get("sslmode")
    if sslmode in {"require", "verify-full", "verify-ca"}:
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        return {"ssl": ssl_context}
    return {}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env.local", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_jwt_secret: str = ""
    backend_cors_origins: str = "http://localhost:3000,http://localhost:8000"

    @property
    def async_database_url(self) -> str:
        return _normalize_postgres_url(
            self.database_url, "asyncpg", ASYNC_QUERY_BLOCKLIST
        )

    @property
    def async_connect_args(self) -> dict:
        return _ssl_connect_args(self.database_url)

    @property
    def sync_database_url(self) -> str:
        return _normalize_postgres_url(self.database_url, "psycopg2")

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.backend_cors_origins.split(",")
            if origin.strip()
        ]

    @property
    def supabase_configured(self) -> bool:
        return bool(
            self.supabase_url
            and self.supabase_anon_key
            and self.supabase_jwt_secret
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
