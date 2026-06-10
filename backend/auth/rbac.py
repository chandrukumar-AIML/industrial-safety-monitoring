"""
backend/auth/rbac.py

Role-Based Access Control (RBAC) for Industrial Safety Monitor.

Roles (least → most privileged):
  viewer   — read-only dashboards, no PII
  operator — viewer + acknowledge violations, trigger reports
  manager  — operator + manage workers, zones, cameras, export data
  admin    — full access including user management, API keys, webhooks, system config

Usage:
    from ..auth.rbac import require_role, Role

    @router.delete("/{id}")
    async def delete_something(
        _: None = Depends(require_role(Role.ADMIN)),
    ):
        ...

API Key authentication:
  Pass key in header:  X-API-Key: <key>
  Or query param:      ?api_key=<key>

Environment:
  RBAC_ENABLED=true   — enforce roles (default: false for backward compat)
  ADMIN_API_KEY       — master admin key (set in production)
"""

from __future__ import annotations

import hashlib
import os
import secrets
from enum import IntEnum
from typing import Optional

from fastapi import Depends, Header, HTTPException, Query, status
from loguru import logger

# ── Config ────────────────────────────────────────────────────
RBAC_ENABLED = os.getenv("RBAC_ENABLED", "false").lower() == "true"
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")

if not ADMIN_API_KEY and RBAC_ENABLED:
    logger.warning(
        "RBAC_ENABLED=true but ADMIN_API_KEY is not set — "
        "admin endpoints will be inaccessible. Set ADMIN_API_KEY in .env"
    )


class Role(IntEnum):
    """Privilege levels — higher value = more access."""
    VIEWER = 1
    OPERATOR = 2
    MANAGER = 3
    ADMIN = 4


# Human-readable names
ROLE_NAMES = {
    Role.VIEWER: "viewer",
    Role.OPERATOR: "operator",
    Role.MANAGER: "manager",
    Role.ADMIN: "admin",
}

# Static key → role mapping (production: load from DB)
# Format: sha256(key) → Role
_STATIC_KEY_MAP: dict[str, Role] = {}


def _hash_key(key: str) -> str:
    """SHA-256 hash an API key for storage/comparison."""
    return hashlib.sha256(key.encode()).hexdigest()


def _load_static_keys() -> None:
    """Load static API keys from environment variables."""
    global _STATIC_KEY_MAP
    _STATIC_KEY_MAP = {}

    if ADMIN_API_KEY:
        _STATIC_KEY_MAP[_hash_key(ADMIN_API_KEY)] = Role.ADMIN

    # Additional role-keyed env vars: MANAGER_API_KEY, OPERATOR_API_KEY, VIEWER_API_KEY
    for role, env_var in [
        (Role.MANAGER, "MANAGER_API_KEY"),
        (Role.OPERATOR, "OPERATOR_API_KEY"),
        (Role.VIEWER, "VIEWER_API_KEY"),
    ]:
        key = os.getenv(env_var, "")
        if key:
            _STATIC_KEY_MAP[_hash_key(key)] = role
            logger.debug("Loaded {} key from env", ROLE_NAMES[role])


_load_static_keys()


def resolve_role(api_key: str) -> Optional[Role]:
    """
    Resolve an API key to a Role.
    Returns None if key is invalid.
    """
    if not api_key:
        return None
    hashed = _hash_key(api_key)
    return _STATIC_KEY_MAP.get(hashed)


def generate_api_key() -> str:
    """Generate a cryptographically secure API key."""
    return "sm_" + secrets.token_urlsafe(32)


# ── FastAPI Dependency ────────────────────────────────────────

def _extract_api_key(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    api_key: Optional[str] = Query(default=None, include_in_schema=False),
) -> Optional[str]:
    """Extract API key from header or query param."""
    return x_api_key or api_key


def require_role(minimum_role: Role):
    """
    FastAPI dependency factory — enforces minimum role.

    If RBAC_ENABLED=false (default), all requests are granted admin-level access
    for backward compatibility. Set RBAC_ENABLED=true in production.

    Usage:
        @router.delete("/{id}")
        async def delete(
            _: None = Depends(require_role(Role.ADMIN)),
        ):
            ...
    """
    async def _check(
        key: Optional[str] = Depends(_extract_api_key),
    ) -> None:
        if not RBAC_ENABLED:
            # RBAC disabled — open access (dev mode)
            return

        if not key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key required. Pass X-API-Key header or ?api_key= query param.",
                headers={"WWW-Authenticate": "ApiKey"},
            )

        role = resolve_role(key)
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid API key.",
            )

        if role < minimum_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient privileges. Required: {ROLE_NAMES[minimum_role]}, "
                       f"your role: {ROLE_NAMES[role]}",
            )

    return _check


def get_current_role(
    key: Optional[str] = Depends(_extract_api_key),
) -> Role:
    """
    Dependency that returns the current role (or ADMIN if RBAC disabled).
    Does NOT raise on missing key — returns VIEWER for unauthenticated.
    """
    if not RBAC_ENABLED:
        return Role.ADMIN
    if not key:
        return Role.VIEWER
    return resolve_role(key) or Role.VIEWER
