"""
tests/test_reports.py

Integration tests for incident report generation.

Role: QA Engineer
Coverage:
  - GET /reports → list
  - GET /reports/stats/summary → stats shape
  - session.execute() regression (was session.exec())
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_reports_returns_list(client):
    """GET /reports must return a JSON list."""
    resp = await client.get("/reports")
    assert resp.status_code == 200, f"GET /reports failed: {resp.text}"
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_reports_stats_summary_shape(client):
    """
    GET /reports/stats/summary must return report statistics.
    Regression: session.exec() vs session.execute() bug caused 500.
    """
    resp = await client.get("/reports/stats/summary")
    assert resp.status_code == 200, (
        f"GET /reports/stats/summary returned {resp.status_code} — "
        f"possible session.exec() regression: {resp.text}"
    )
    data = resp.json()
    assert isinstance(data, dict), "Stats summary must be a JSON object"


@pytest.mark.asyncio
async def test_reports_pagination(client):
    """GET /reports?limit=5 must respect limit."""
    resp = await client.get("/reports?limit=5")
    assert resp.status_code == 200
    assert len(resp.json()) <= 5
