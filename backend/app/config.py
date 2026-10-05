"""
Application configuration via Pydantic Settings.

All config is read from environment variables (or a .env file in the backend/
directory). See .env.example for the full list of supported variables.
"""

from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration — reads from .env automatically."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # silently ignore env vars we don't consume
    )

    # ── Application ──────────────────────────────────────────────
    APP_NAME: str = "RiskLens"
    ENVIRONMENT: str = "dev"  # "dev" | "prod"

    # ── Database ─────────────────────────────────────────────────
    DATABASE_URL: str  # required — no default so missing value is a loud error
    DATABASE_URL_SYNC: str = ""  # auto-derived if not explicitly set

    # ── CORS ─────────────────────────────────────────────────────
    CORS_ORIGINS: str = "http://localhost:3000"

    # ── Auth & JWT ───────────────────────────────────────────────
    JWT_SECRET_KEY: str = "CHANGE_ME_BEFORE_CHUNK_2"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Gemini AI (Chunk 11) ─────────────────────────────────────
    GEMINI_API_KEY: str = ""        # empty = recommendations degrade to "unavailable"
    GEMINI_MODEL: str = "gemini-3.5-flash"

    # ── AI Assistant (Phases 1-2) ────────────────────────────────
    ASSISTANT_MAX_TOOL_ROUNDS: int = 4
    ASSISTANT_RATE_LIMIT_PER_MIN: int = 20
    ASSISTANT_LLM_TIMEOUT_S: int = 20
    ASSISTANT_REQUEST_DEADLINE_S: int = 45

    # ── Derived helpers ──────────────────────────────────────────

    @model_validator(mode="after")
    def _derive_sync_url(self) -> "Settings":
        """
        If DATABASE_URL_SYNC is empty, derive it from DATABASE_URL by
        swapping the async driver (asyncpg) for the sync one (psycopg2).
        """
        if not self.DATABASE_URL_SYNC:
            self.DATABASE_URL_SYNC = self.DATABASE_URL.replace(
                "postgresql+asyncpg", "postgresql+psycopg2"
            )
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse the comma-separated CORS_ORIGINS string into a list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def is_dev(self) -> bool:
        return self.ENVIRONMENT.lower() == "dev"


# Singleton — import this everywhere instead of constructing new instances.
settings = Settings()
