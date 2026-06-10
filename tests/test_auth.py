"""
tests/test_auth.py

Authentication & RBAC security tests.

Role: Security Engineer / QA Engineer
Coverage:
  - Missing Authorization header → 401
  - Wrong token → 403
  - Valid token → 200
  - Public paths bypass auth
"""
from __future__ import annotations

import pytest


PROTECTED_PATHS = [
    "/detections",
    "/workers",
    "/zones",
    "/cameras",
    "/sites",
    "/shifts",
    "/audit",
    "/agent/status",
    "/mlops/models",
]

PUBLIC_PATHS = [
    "/health",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("path", PUBLIC_PATHS)
async def test_public_path_no_auth_needed(unauth_client, path):
    """
    Public endpoints must be accessible without auth.
    Health returns 200 or 503 (degraded in test env without pipeline) — both OK.
    Must never return 401/403.
    """
    resp = await unauth_client.get(path)
    assert resp.status_code not in {401, 403}, (
        f"{path} returned auth error {resp.status_code} — must be public"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("path", PROTECTED_PATHS)
async def test_protected_path_without_token_returns_401(unauth_client, path):
    """Protected endpoints must reject requests with no Authorization header."""
    resp = await unauth_client.get(path)
    assert resp.status_code in {401, 403}, (
        f"{path} should require auth but returned {resp.status_code}"
    )


@pytest.mark.asyncio
async def test_wrong_token_returns_403(unauth_client):
    """Wrong Bearer token must return 403 Forbidden."""
    resp = await unauth_client.get(
        "/detections",
        headers={"Authorization": "Bearer wrong-token-abc123"},
    )
    assert resp.status_code == 403, f"Expected 403 but got {resp.status_code}"


@pytest.mark.asyncio
async def test_malformed_auth_header_returns_401(unauth_client):
    """Malformed header (no 'Bearer ' prefix) must return 401."""
    resp = await unauth_client.get(
        "/detections",
        headers={"Authorization": "Token abc123"},
    )
    assert resp.status_code in {401, 403}


@pytest.mark.asyncio
@pytest.mark.parametrize("path", PROTECTED_PATHS)
async def test_valid_token_grants_access(client, path):
    """Valid Bearer token must grant access to protected endpoints."""
    resp = await client.get(path)
    # Any non-401/403 means auth passed (could be 200, 404, 422 etc.)
    assert resp.status_code not in {401, 403}, (
        f"{path} rejected valid token with {resp.status_code}"
    )
