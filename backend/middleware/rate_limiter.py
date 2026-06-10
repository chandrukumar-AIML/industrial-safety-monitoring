"""
backend/middleware/rate_limiter.py

API Rate Limiting — prevents abuse and protects inference resources.

Role: Security Engineer

Implementation: slowapi (Starlette-native, Redis-compatible)

Limits (per IP):
  - Default API endpoints:  60 requests / minute
  - Auth-sensitive paths:   10 requests / minute  (login attempts)
  - Inference endpoints:    20 requests / minute  (expensive GPU/CPU ops)
  - Export endpoints:       5  requests / minute  (large file generation)
  - Chatbot:               10 requests / minute  (LLM calls are expensive)

Usage in routes:
    from backend.middleware.rate_limiter import limiter
    from slowapi import _rate_limit_exceeded_handler

    @router.get("/endpoint")
    @limiter.limit("60/minute")
    async def my_endpoint(request: Request):
        ...

Notes:
  - In development (API_KEY empty), rate limits are still enforced
    but use IP 127.0.0.1 for all local requests
  - For production with multiple workers, use Redis backend:
    limiter = Limiter(key_func=get_remote_address, storage_uri="redis://localhost:6379")
"""
from __future__ import annotations

import os
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# ── Limiter instance ─────────────────────────────────────────
# In production with Redis: storage_uri="redis://localhost:6379"
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200/minute"],  # Global fallback
    # Uncomment for Redis:
    # storage_uri=os.getenv("REDIS_URL", "memory://"),
)

# ── Predefined limit strings ──────────────────────────────────
# Reference these in route decorators for consistency
LIMIT_DEFAULT = "60/minute"
LIMIT_INFERENCE = "20/minute"    # SHAP, heatmap — expensive
LIMIT_EXPORT = "5/minute"        # CSV export — large files
LIMIT_CHATBOT = "10/minute"      # LLM calls — cost-sensitive
LIMIT_AUTH = "10/minute"         # Auth endpoints — brute-force protection
LIMIT_REPORTS = "10/minute"      # Report generation — LLM + PDF


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """
    Custom handler for rate limit exceeded errors.
    Returns RFC 6585 compliant 429 response with Retry-After header.
    """
    retry_after = getattr(exc, "retry_after", 60)
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "detail": [{
                "message": (
                    f"Too many requests. Rate limit: {exc.detail}. "
                    f"Retry after {retry_after} seconds."
                )
            }],
        },
        headers={
            "Retry-After": str(retry_after),
            "X-RateLimit-Limit": str(exc.detail),
        },
    )
