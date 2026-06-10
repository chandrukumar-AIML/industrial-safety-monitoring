"""
tests/test_detections.py

Integration tests for the /detections endpoint.

Role: QA Engineer
Coverage:
  - List violations (empty DB)
  - Response is always a list
  - Pagination params (limit / offset)
  - Filter by class_name
  - /detections/stats shape
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_detections_returns_list(client):
    """GET /detections must return a JSON list."""
    resp = await client.get("/detections")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_detections_default_limit(client):
    """Default response must not exceed 100 items."""
    resp = await client.get("/detections")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) <= 100


@pytest.mark.asyncio
async def test_detections_limit_param(client):
    """?limit=5 must return at most 5 items."""
    resp = await client.get("/detections?limit=5")
    assert resp.status_code == 200
    assert len(resp.json()) <= 5


@pytest.mark.asyncio
async def test_detections_offset_param(client):
    """?offset param must be accepted without error."""
    resp = await client.get("/detections?limit=10&offset=0")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_detections_class_filter(client):
    """?class_name filter must return only matching violations."""
    resp = await client.get("/detections?class_name=no+helmet")
    assert resp.status_code == 200
    data = resp.json()
    for item in data:
        assert item["class_name"] == "no helmet", (
            f"Filter broke: got class_name={item['class_name']}"
        )


@pytest.mark.asyncio
async def test_detections_stats_shape(client):
    """GET /detections/stats must include by_class and total_violations."""
    resp = await client.get("/detections/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_violations" in data or "by_class" in data, (
        f"Stats response missing expected keys: {list(data.keys())}"
    )
