"""
tests/test_zones.py

Integration tests for zone management.

Role: QA Engineer
Coverage:
  - GET /zones → always returns list (never 500)
  - POST /zones → create zone with zone_type
  - zone_type NULL regression guard
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_list_zones_returns_list(client):
    """GET /zones must return a JSON list, never 500."""
    resp = await client.get("/zones")
    assert resp.status_code == 200, (
        f"GET /zones returned {resp.status_code} — possible NULL zone_type regression"
    )
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_create_zone(client):
    """POST /zones must create a zone with required zone_type field."""
    payload = {
        "zone_id": "zone-test-01",
        "zone_name": "Test Restricted Zone",
        "zone_type": "restricted",
        "required_ppe": ["helmet", "vest"],
        "camera_id": "cam-test-001",
        "polygon_norm": [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0},
                         {"x": 1.0, "y": 1.0}, {"x": 0.0, "y": 1.0}],
    }
    resp = await client.post("/zones", json=payload)
    assert resp.status_code in {200, 201}, f"Create zone failed: {resp.text}"
    data = resp.json()
    assert data.get("zone_type") is not None, "zone_type must not be NULL"


@pytest.mark.asyncio
async def test_zone_type_never_null(client):
    """Every zone in GET /zones must have a non-null zone_type."""
    resp = await client.get("/zones")
    assert resp.status_code == 200
    for zone in resp.json():
        assert zone.get("zone_type") is not None, (
            f"Zone {zone.get('zone_id')} has NULL zone_type — regression!"
        )
