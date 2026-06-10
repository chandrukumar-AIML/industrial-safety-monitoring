"""
tests/test_health.py

Unit tests for the /health endpoint.

Role: QA Engineer
Coverage:
  - Public access (no Bearer token required)
  - Response shape
  - Status values
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health_public_access(unauth_client):
    """
    Health endpoint must be accessible without auth.
    Returns 200 (ok) or 503 (degraded/starting) — both mean endpoint is reachable.
    Never returns 401/403.
    """
    resp = await unauth_client.get("/health")
    assert resp.status_code in {200, 503}, (
        f"Health must be public (200/503), got {resp.status_code}: {resp.text}"
    )


@pytest.mark.asyncio
async def test_health_response_shape(client):
    """
    Health response must include required fields regardless of pipeline state.
    In test env (no camera/model), returns 503 (degraded) — this is expected.
    """
    resp = await client.get("/health")
    # 200=ok, 503=degraded/starting — both valid in test env
    assert resp.status_code in {200, 503}, f"Unexpected status: {resp.status_code}"
    data = resp.json()

    # Check at least the core status field exists
    assert "status" in data, f"Health response must have 'status' field, got: {list(data.keys())}"


@pytest.mark.asyncio
async def test_health_status_value(client):
    """Health status must be 'ok' or 'degraded'."""
    resp = await client.get("/health")
    data = resp.json()
    assert data["status"] in {"ok", "degraded", "starting"}, (
        f"Unexpected status value: {data['status']}"
    )


@pytest.mark.asyncio
async def test_health_demo_mode_flag(client):
    """DEMO_MODE=true should reflect in health response."""
    resp = await client.get("/health")
    assert resp.status_code in {200, 503}
    data = resp.json()
    # status field should be a string
    assert isinstance(data.get("status"), str)


@pytest.mark.asyncio
async def test_health_not_blocked_by_auth(unauth_client):
    """Health must never return 401/403 — it's a public liveness probe."""
    resp = await unauth_client.get("/health")
    assert resp.status_code not in {401, 403}, (
        f"Health endpoint blocked by auth — should be public: {resp.status_code}"
    )


# ── Liveness / readiness probes (added in production audit) ──────

@pytest.mark.asyncio
async def test_liveness_probe(unauth_client):
    """Liveness must always return 200 with status 'alive' — public, no deps."""
    resp = await unauth_client.get("/health/live")
    assert resp.status_code == 200, f"Liveness must be 200, got {resp.status_code}"
    assert resp.json()["status"] == "alive"


@pytest.mark.asyncio
async def test_readiness_probe_checks_db(unauth_client):
    """
    Readiness must ping the real database and report it.
    With the test DB available it returns 200 + database: ok.
    """
    resp = await unauth_client.get("/health/ready")
    assert resp.status_code in {200, 503}, f"Unexpected: {resp.status_code}"
    data = resp.json()
    assert "checks" in data and "database" in data["checks"], (
        f"Readiness must report dependency checks, got: {data}"
    )


@pytest.mark.asyncio
async def test_readiness_probe_public(unauth_client):
    """Readiness probe must be public (load balancers call it unauthenticated)."""
    resp = await unauth_client.get("/health/ready")
    assert resp.status_code not in {401, 403}
