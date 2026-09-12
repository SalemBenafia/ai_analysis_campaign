"""
app/core/settings.py
=====================
Central configuration via pydantic-settings.
All values read from environment variables or .env file — never hardcoded.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any, List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── App ──────────────────────────────────────────────────────────────────
    APP_NAME: str = "InsightAI"
    APP_ENV: str = "development"
    DEBUG: bool = False
    SECRET_KEY: str = Field(..., min_length=32)
    API_V1_PREFIX: str = "/api/v1"

    # ─── CORS ─────────────────────────────────────────────────────────────────
    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost:3000"]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            import json
            return json.loads(v)
        return v

    # ─── JWT ──────────────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = Field(..., min_length=32)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ─── Cookie ───────────────────────────────────────────────────────────────
    ACCESS_COOKIE_NAME: str = "access_token"
    REFRESH_COOKIE_NAME: str = "refresh_token"
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"
    COOKIE_DOMAIN: Optional[str] = None

    # ─── Database (PostgreSQL — OLTP) ─────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://insight:insight_secret@localhost:5433/insightai"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_ECHO: bool = False

    # ─── DuckDB (OLAP analytics engine — in-process) ─────────────────────────
    DUCKDB_PATH: str = "/app/duckdb_data/analytics.db"
    DUCKDB_MEMORY_LIMIT: str = "256MB"
    DUCKDB_THREADS: int = 1

    # ─── Redis ────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CACHE_TTL: int = 300

    # ─── MinIO ────────────────────────────────────────────────────────────────
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ROOT_USER: str = "minioadmin"
    MINIO_ROOT_PASSWORD: str = "minio_secret_123"
    MINIO_BUCKET_DATASETS: str = "insightai-datasets"
    MINIO_BUCKET_REPORTS: str = "insightai-reports"
    MINIO_SECURE: bool = False

    # ─── AI / Groq ────────────────────────────────────────────────────────────
    # GROQ_MODELS is an ordered, comma-separated pool. When a model hits its
    # rate limit it is put on cooldown (Redis) and the next model takes over.
    GROQ_API_KEY: str = ""
    GROQ_MODELS: str = (
        "llama-3.3-70b-versatile,"
        "openai/gpt-oss-120b,"
        "meta-llama/llama-4-scout-17b-16e-instruct,"
        "llama-3.1-8b-instant"
    )
    GROQ_REQUEST_TIMEOUT: int = 30
    GROQ_MAX_TOKENS: int = 1500
    GROQ_COOLDOWN_SECONDS: int = 60  # default cooldown when no retry-after header

    @property
    def groq_model_pool(self) -> List[str]:
        return [m.strip() for m in self.GROQ_MODELS.split(",") if m.strip()]

    # ─── Semantic Layer / Cube ────────────────────────────────────────────────
    CUBE_API_URL: str = "http://cube:4000"
    CUBEJS_API_SECRET: str = ""       # shared with the cube container (JWT signing)
    CUBE_INTERNAL_TOKEN: str = ""     # guards /internal/cube/* model endpoints
    CUBE_LOAD_TIMEOUT: int = 20       # seconds budget for Continue-wait long-poll
    SEMANTIC_ENGINE: str = "cube"     # cube | duckdb (duckdb also used as auto-fallback)

    # ─── Transform (dbt) ──────────────────────────────────────────────────────
    DBT_ENABLED: bool = True          # falls back to Polars transform when False/failing
    DBT_PROJECT_DIR: str = "/app/dbt"

    # ─── Scheduler ────────────────────────────────────────────────────────────
    SCHEDULER_ENABLED: bool = True    # APScheduler in-process (single worker only)

    # ─── Analytics Defaults ───────────────────────────────────────────────────
    MAX_QUERY_ROWS: int = 10_000
    MAX_UPLOAD_MB: int = 50

    # ─── Logging ──────────────────────────────────────────────────────────────
    LOG_LEVEL: str = "DEBUG"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
