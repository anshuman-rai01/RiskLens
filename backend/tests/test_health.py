"""
Automated tests for health check endpoint and error message sanitization.
"""

from __future__ import annotations

import logging
import httpx
import pytest
from unittest.mock import AsyncMock

from app.database import get_db
from app.main import app


@pytest.mark.asyncio
async def test_health_healthy():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["db"] == "connected"


@pytest.mark.asyncio
async def test_health_db_down_sanitized(caplog):
    """
    Simulate database failure and confirm raw exception strings
    (such as passwords, internal paths, or connection strings) do not leak to client.
    """
    mock_db = AsyncMock()
    secret_error = "FATAL: password authentication failed for user 'postgres' at localhost:5432"
    mock_db.execute.side_effect = RuntimeError(secret_error)

    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            with caplog.at_level(logging.ERROR):
                resp = await client.get("/health")
                assert resp.status_code == 503
                data = resp.json()
                assert data["status"] == "error"
                assert data["db"] == "disconnected"
                assert data["detail"] == "Unable to connect to the database"
                # Crucial security verification: raw exception details must NOT be in client response
                assert secret_error not in resp.text
                # But must be present in server-side logs
                assert secret_error in caplog.text
    finally:
        app.dependency_overrides.pop(get_db, None)
