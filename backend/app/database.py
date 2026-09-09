"""
Async SQLAlchemy engine and session dependency for FastAPI.

Usage in a router:
    from app.database import get_db
    from sqlalchemy.ext.asyncio import AsyncSession

    @router.get("/example")
    async def example(db: AsyncSession = Depends(get_db)):
        ...
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

# ── Engine ───────────────────────────────────────────────────────
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.is_dev,      # log SQL statements in dev mode
    pool_pre_ping=True,        # verify connections are alive before use
)

# ── Session factory ──────────────────────────────────────────────
async_session = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── FastAPI dependency ───────────────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield an async session per-request, ensuring it is always closed
    even if the request handler raises an exception.
    """
    session = async_session()
    try:
        yield session
    finally:
        await session.close()
