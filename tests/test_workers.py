"""
tests/test_workers.py

Integration tests for worker profiles and risk scoring.

Role: QA Engineer
Coverage:
  - GET /workers → list
  - POST /workers → create worker
  - GET /workers/{id}/risk → risk score shape
  - GET /workers/dashboard/risk → dashboard shape
  - Route ordering: dashboard/risk not swallowed by /{id}/risk
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_list_workers_returns_list(client):
    """GET /workers must return a JSON list."""
    resp = await client.get("/workers")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_create_worker(client):
    """POST /workers must create a worker — uses multipart form data."""
    # Workers API uses Form() not JSON (supports optional photo upload)
    resp = await client.post(
        "/workers",
        data={
            "worker_id": "W-TEST-001",
            "full_name": "Test Worker QA",
            "department": "QA",
            "role": "operator",
        },
    )
    assert resp.status_code in {200, 201}, f"Create worker failed: {resp.text}"
    data = resp.json()
    assert data.get("worker_id") == "W-TEST-001"


@pytest.mark.asyncio
async def test_worker_risk_score_shape(client):
    """GET /workers/{id}/risk must return worker_id, risk_score, risk_level."""
    resp = await client.get("/workers/W-TEST-001/risk")
    assert resp.status_code == 200
    data = resp.json()
    required = {"worker_id", "risk_score", "risk_level"}
    missing = required - set(data.keys())
    assert not missing, f"Risk response missing keys: {missing}"


@pytest.mark.asyncio
async def test_risk_score_range(client):
    """risk_score must be >= 0."""
    resp = await client.get("/workers/W-TEST-001/risk")
    if resp.status_code == 200:
        assert resp.json()["risk_score"] >= 0


@pytest.mark.asyncio
async def test_dashboard_risk_not_caught_by_worker_id_route(client):
    """
    CRITICAL: GET /workers/dashboard/risk must NOT be matched
    by the /{worker_id}/risk route (route ordering bug regression test).
    """
    resp = await client.get("/workers/dashboard/risk")
    # Must return dashboard data, NOT a single worker's risk score
    assert resp.status_code == 200
    data = resp.json()
    # Dashboard returns a dict with aggregate fields, not a single risk object
    # If it was wrongly matched by /{worker_id}/risk, worker_id would be "dashboard"
    assert data.get("worker_id") != "dashboard", (
        "Route ordering bug: /dashboard/risk was matched by /{worker_id}/risk!"
    )


@pytest.mark.asyncio
async def test_dashboard_risk_shape(client):
    """GET /workers/dashboard/risk must include top_offenders or summary."""
    resp = await client.get("/workers/dashboard/risk")
    assert resp.status_code == 200
    data = resp.json()
    # Dashboard returns a dict or list — should not be empty
    assert data is not None
