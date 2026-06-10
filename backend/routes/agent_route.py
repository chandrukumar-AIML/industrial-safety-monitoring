"""
backend/routes/agent_route.py

Agent management endpoints:
  - GET  /agent/runs          — list recent agent runs
  - GET  /agent/runs/{run_id} — get one run with full trace
  - POST /agent/trigger       — manually trigger agent
  - GET  /agent/status        — agent health + concurrency

# FIXED: Input validation + sanitization for all public methods
# FIXED: Parameterized queries only — no SQL injection
# IMPROVED: Rate limiting for trigger endpoint
# IMPROVED: Dependency injection for testability
# FIXED: No PII leakage in logs
"""

from __future__ import annotations

import json
import os
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession
from loguru import logger

from ..database import get_session

router = APIRouter(prefix="/agent", tags=["agent"])

# ── Rate limiting config ─────────────────────────────────────
_RATE_LIMIT_MAX = int(os.getenv("AGENT_TRIGGER_RATE_LIMIT", "10"))
_RATE_LIMIT_WINDOW_S = float(os.getenv("AGENT_TRIGGER_RATE_LIMIT_WINDOW", "60"))
_rate_store: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(client_ip: str) -> None:
    """Simple sliding window rate limiter."""
    now = time.monotonic()
    window = _rate_store.get(client_ip, [])
    _rate_store[client_ip] = [t for t in window if now - t < _RATE_LIMIT_WINDOW_S]
    
    if len(_rate_store[client_ip]) >= _RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit: {_RATE_LIMIT_MAX} triggers per {_RATE_LIMIT_WINDOW_S}s",
            headers={"Retry-After": str(int(_RATE_LIMIT_WINDOW_S))},
        )
    _rate_store[client_ip].append(now)


# ── Response models ───────────────────────────────────────────
class AgentRunOut(BaseModel):
    id: int
    run_id: str
    track_id: Optional[int]
    class_name: Optional[str]
    severity_score: Optional[int]
    alert_level: Optional[str]
    report_id: Optional[int]
    alert_sent: bool
    compliance_delta: Optional[float]
    final_status: Optional[str]
    error: Optional[str]
    created_at: str
    trace_steps: Optional[List[dict]] = None


class ManualTriggerRequest(BaseModel):
    track_id: int = Field(ge=0)
    class_name: str = Field(min_length=1, max_length=100)
    confidence: float = Field(ge=0.0, le=1.0, default=0.85)
    zone_id: Optional[str] = Field(default=None, max_length=100)
    frame_idx: int = Field(default=0, ge=0)
    
    @field_validator("class_name")
    @classmethod
    def validate_class_name(cls, v: str) -> str:
        if not re.match(r'^[a-zA-Z0-9\s\-]+$', v):
            raise ValueError("class_name contains invalid characters")
        return v.strip()


class AgentStatusOut(BaseModel):
    enabled: bool
    langsmith_enabled: bool
    max_concurrent: int
    model: str
    severity_threshold: int


# ── Endpoints ─────────────────────────────────────────────────
@router.get(
    "/runs",
    response_model=List[AgentRunOut],
    summary="List recent agent runs",
)
async def list_agent_runs(
    limit: int = Query(default=50, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> list:
    """List most recent agent runs with summary."""
    result = await session.execute(
        text("""
            SELECT id, run_id, track_id, class_name,
                   severity_score, alert_level, report_id,
                   alert_sent, compliance_delta, final_status,
                   error, created_at
            FROM agent_runs
            ORDER BY created_at DESC
            LIMIT :limit
        """),
        {"limit": limit}
    )
    return [
        {
            **dict(row),
            "created_at": str(row["created_at"]),
            "trace_steps": None,
        }
        for row in result.mappings().all()
    ]


@router.get(
    "/runs/{run_id}",
    response_model=AgentRunOut,
    summary="Get agent run with full trace",
)
async def get_agent_run(
    run_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Get one agent run including full trace_steps audit log."""
    # Validate run_id format
    if not re.match(r'^[a-zA-Z0-9\-]+$', run_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid run_id format")
    
    result = await session.execute(
        text("SELECT * FROM agent_runs WHERE run_id = :run_id"),
        {"run_id": run_id}
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")

    return {
        **dict(row),
        "created_at": str(row["created_at"]),
        "trace_steps": json.loads(row["trace_steps"]) if row["trace_steps"] else [],
    }


@router.post(
    "/trigger",
    summary="Manually trigger safety agent",
    description=(
        "Trigger the safety agent manually for testing or "
        "re-processing a specific violation. "
        "The agent runs asynchronously — response returns immediately."
    ),
)
async def manual_trigger(
    body: ManualTriggerRequest,
    request: Request,
) -> dict:
    """Manually trigger the safety agent."""
    # Rate limit check
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)
    
    # Import here to avoid circular dependency
    from ..agent.runner import trigger_from_violation

    # FIXED: Capture return value; if coroutine, await it; log errors properly
    try:
        result = trigger_from_violation(
            track_id=body.track_id,
            class_name=body.class_name,
            confidence=body.confidence,
            zone_id=body.zone_id,
            frame_idx=body.frame_idx,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        import asyncio, inspect
        if inspect.isawaitable(result):
            await result
    except Exception as exc:
        logger.error("trigger_from_violation failed: {}", exc)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Agent trigger failed: {type(exc).__name__}")

    return {
        "status": "triggered",
        "track_id": body.track_id,
        "class_name": body.class_name,
        "message": "Agent running in background — check /agent/runs",
    }


@router.get(
    "/status",
    response_model=AgentStatusOut,
    summary="Agent configuration status",
)
async def agent_status() -> AgentStatusOut:
    """Return agent configuration and status."""
    return AgentStatusOut(
        enabled=True,
        langsmith_enabled=bool(os.getenv("LANGCHAIN_API_KEY")),
        max_concurrent=int(os.getenv("AGENT_MAX_CONCURRENT_RUNS", "3")),
        model=os.getenv("AGENT_LLM_MODEL", "llama3"),
        severity_threshold=int(os.getenv("AGENT_SEVERITY_THRESHOLD", "5")),
    )


def get_diagnostics() -> dict:
    """Return router status for health checks."""
    return {
        "rate_limit": {
            "max": _RATE_LIMIT_MAX,
            "window_s": _RATE_LIMIT_WINDOW_S,
            "active_ips": len(_rate_store),
        },
    }