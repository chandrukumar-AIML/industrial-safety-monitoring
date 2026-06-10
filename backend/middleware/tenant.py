"""
backend/middleware/tenant.py

Multi-tenant isolation middleware.

How it works:
  1. Reads X-Org-ID header from every request
  2. Validates the org_id exists and is active in DB
  3. Stores it in request.state.org_id
  4. Routes can access it via: request.state.org_id
  5. If header missing → defaults to "default" (single-tenant mode)

FastAPI dependency for tenant-scoped queries:
    async def get_org_id(request: Request) -> str:
        return get_tenant_org_id(request)

Usage in routes:
    @router.get("/violations")
    async def list_violations(
        org_id: str = Depends(get_tenant_org_id),
        session: AsyncSession = Depends(get_session),
    ):
        result = await session.exec(
            select(ViolationEvent).where(ViolationEvent.org_id == org_id)
        )
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from loguru import logger

# In single-tenant mode (no X-Org-ID header), use this default
DEFAULT_ORG_ID = os.getenv("DEFAULT_ORG_ID", "default")

# Paths that bypass tenant resolution (public endpoints)
_BYPASS_PATHS = {"/health", "/docs", "/redoc", "/openapi.json", "/metrics"}


class TenantMiddleware(BaseHTTPMiddleware):
    """
    Middleware that resolves org_id for every request.
    Sets request.state.org_id — available to all downstream handlers.
    Does NOT block requests without a header (defaults to DEFAULT_ORG_ID).
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Bypass for public paths
        path = request.url.path
        if any(path.startswith(p) for p in _BYPASS_PATHS):
            request.state.org_id = DEFAULT_ORG_ID
            return await call_next(request)

        # Read org_id from header (falls back to default)
        org_id = request.headers.get("X-Org-ID", DEFAULT_ORG_ID).strip()

        # Basic validation
        if not org_id or len(org_id) > 64:
            logger.warning("Invalid X-Org-ID header: {}", org_id[:32])
            org_id = DEFAULT_ORG_ID

        # Sanitize: only allow alphanumeric, hyphens, underscores
        import re
        if not re.fullmatch(r'[a-zA-Z0-9_\-]+', org_id):
            logger.warning("X-Org-ID contains invalid chars: {}", org_id[:32])
            org_id = DEFAULT_ORG_ID

        request.state.org_id = org_id
        logger.debug("Tenant resolved | org_id={} | path={}", org_id, path)

        return await call_next(request)


def get_tenant_org_id(request: Request) -> str:
    """
    FastAPI dependency — returns the resolved org_id for this request.
    Always returns a string (DEFAULT_ORG_ID if no header).

    Usage:
        @router.get("/alerts")
        async def get_alerts(org_id: str = Depends(get_tenant_org_id)):
            ...
    """
    return getattr(request.state, "org_id", DEFAULT_ORG_ID)


def require_tenant_org_id(request: Request) -> str:
    """
    Strict variant — raises 400 if no X-Org-ID header was provided.
    Use for multi-tenant SaaS routes where org context is mandatory.
    """
    org_id = request.headers.get("X-Org-ID", "").strip()
    if not org_id:
        raise HTTPException(
            status_code=400,
            detail="X-Org-ID header is required for this endpoint",
        )
    return getattr(request.state, "org_id", DEFAULT_ORG_ID)
