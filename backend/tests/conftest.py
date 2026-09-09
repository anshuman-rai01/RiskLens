"""
Pytest configuration and fixtures for backend test suite.
"""

import pytest_asyncio
from app.database import engine


@pytest_asyncio.fixture(autouse=True)
async def cleanup_db_connections():
    """Ensure database connection pool is disposed after each async test."""
    yield
    await engine.dispose()
