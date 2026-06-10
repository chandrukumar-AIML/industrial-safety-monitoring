"""
tests/test_mlops.py

Integration tests for MLOps endpoints.

Role: QA Engineer / ML Engineer
Coverage:
  - GET /mlops/models → list
  - GET /mlops/canary/status → canary deployment info
  - asyncio import regression (canary_router.py)
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_list_models_returns_list(client):
    """GET /mlops/models must return a JSON list."""
    resp = await client.get("/mlops/models")
    assert resp.status_code == 200, f"GET /mlops/models failed: {resp.text}"
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_canary_status_shape(client):
    """
    GET /mlops/canary/status must return canary deployment info.
    Regression: asyncio.Lock() in canary_router.py without 'import asyncio'.
    """
    resp = await client.get("/mlops/canary/status")
    assert resp.status_code == 200, (
        f"GET /mlops/canary/status returned {resp.status_code} — "
        f"possible missing 'import asyncio' regression: {resp.text}"
    )
    data = resp.json()
    # Should have some canary-related field
    assert isinstance(data, dict), "Canary status must be a JSON object"


@pytest.mark.asyncio
async def test_agent_status_shape(client):
    """GET /agent/status must return agent configuration."""
    resp = await client.get("/agent/status")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)


@pytest.mark.asyncio
async def test_agent_runs_returns_list(client):
    """GET /agent/runs must return a JSON list."""
    resp = await client.get("/agent/runs")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
