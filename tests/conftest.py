"""
tests/conftest.py

Shared pytest fixtures for all test modules.

Strategy:
  - Use file-based SQLite (not :memory:) so tables persist across connections
  - App's own init_db() creates all tables
  - Cleanup the test DB file after session
"""
from __future__ import annotations

import os
import pytest
import pytest_asyncio

# Use a dedicated file-based test DB (not :memory: — doesn't share across connections)
TEST_DB_PATH = "./test_safety_monitor.db"

# ── CRITICAL: Set env vars BEFORE any app import ─────────────
os.environ["API_KEY"] = "test-api-key-for-pytest"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest-only"
os.environ["ENVIRONMENT"] = "test"
os.environ["DEMO_MODE"] = "true"
os.environ["MODEL_PATH"] = "models/best.pt"
os.environ["VIDEO_SOURCE"] = "0"
os.environ["MLFLOW_TRACKING_URI"] = "sqlite:///mlflow/mlflow.db"

TEST_API_KEY = os.environ["API_KEY"]
AUTH_HEADERS = {"Authorization": f"Bearer {TEST_API_KEY}"}


@pytest_asyncio.fixture(scope="session", autouse=True)
async def init_test_database():
    """
    Initialize the test database once per session.
    Uses the app's own init_db() to create all tables.
    """
    from backend.database import init_db, engine
    await init_db(engine)
    yield
    # Cleanup: dispose engine and remove test DB file
    await engine.dispose()
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass  # Windows may lock the file; ignore cleanup failure


@pytest_asyncio.fixture
async def client():
    """
    Async HTTP client with Bearer auth header pre-set.
    ASGI transport — no real HTTP server needed.
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers=AUTH_HEADERS,
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def unauth_client():
    """Client with NO auth header — for testing 401/403 responses."""
    from httpx import AsyncClient, ASGITransport
    from backend.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
