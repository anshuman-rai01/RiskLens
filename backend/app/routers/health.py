"""
Health-check router.

GET /health — verifies the app can reach the database.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """
    Execute a trivial ``SELECT 1`` to prove the DB connection is live.

    Returns:
        200  {"status": "ok",    "db": "connected"}
        503  {"status": "error", "db": "disconnected", "detail": "Unable to connect to the database"}
    """
    try:
        await db.execute(text("SELECT 1"))
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "ok", "db": "connected"},
        )
    except Exception as exc:
        logger.error("Database health check failed: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "error",
                "db": "disconnected",
                "detail": "Unable to connect to the database",
            },
        )

