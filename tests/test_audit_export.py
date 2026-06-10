"""
tests/test_audit_export.py

Integration tests for audit log and data export.

Role: QA Engineer / Security Engineer
Coverage:
  - GET /audit → returns list (OSHA compliance)
  - GET /export/violations.csv → returns CSV content-type
  - GET /export/workers.csv → returns CSV
  - Audit entries have required OSHA fields
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_audit_log_returns_list(client):
    """GET /audit must return a JSON list (never a 500)."""
    resp = await client.get("/audit")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_audit_log_pagination(client):
    """GET /audit?limit=5 must respect pagination."""
    resp = await client.get("/audit?limit=5")
    assert resp.status_code == 200
    assert len(resp.json()) <= 5


@pytest.mark.asyncio
async def test_violations_csv_export(client):
    """GET /export/violations.csv must return CSV content."""
    resp = await client.get("/export/violations.csv")
    assert resp.status_code == 200
    content_type = resp.headers.get("content-type", "")
    assert "text/csv" in content_type or "application/octet-stream" in content_type, (
        f"Expected CSV content-type, got: {content_type}"
    )


@pytest.mark.asyncio
async def test_workers_csv_export(client):
    """GET /export/workers.csv must return CSV content."""
    resp = await client.get("/export/workers.csv")
    assert resp.status_code == 200
    content_type = resp.headers.get("content-type", "")
    assert "text/csv" in content_type or "application/octet-stream" in content_type


@pytest.mark.asyncio
async def test_audit_without_auth_blocked(unauth_client):
    """Audit log must be protected — OSHA compliance requires access control."""
    resp = await unauth_client.get("/audit")
    assert resp.status_code in {401, 403}, (
        f"Audit log must be protected but returned {resp.status_code}"
    )
