"""
tests/test_sites_shifts.py

Integration tests for multi-site and shift management.

Role: QA Engineer
Coverage:
  - POST /sites → create site
  - GET /sites → list
  - POST /shifts → create shift
  - GET /shifts → list
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_create_site(client):
    """POST /sites must create a site and return it."""
    payload = {
        "site_id": "site-test-hq",
        "site_name": "Test HQ",
        "location": "Chennai, TN",
        "country": "India",
        "timezone": "Asia/Kolkata",
    }
    resp = await client.post("/sites", json=payload)
    assert resp.status_code in {200, 201}, f"Create site failed: {resp.text}"
    data = resp.json()
    assert data.get("site_id") == "site-test-hq"


@pytest.mark.asyncio
async def test_list_sites_returns_list(client):
    """GET /sites must return a JSON list."""
    resp = await client.get("/sites")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_create_shift(client):
    """POST /shifts must create a shift."""
    payload = {
        "shift_name": "Morning Shift",
        "site_id": "site-test-hq",
        "start_time": "06:00",
        "end_time": "14:00",
    }
    resp = await client.post("/shifts", json=payload)
    assert resp.status_code in {200, 201}, f"Create shift failed: {resp.text}"


@pytest.mark.asyncio
async def test_list_shifts_returns_list(client):
    """GET /shifts must return a JSON list."""
    resp = await client.get("/shifts")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
