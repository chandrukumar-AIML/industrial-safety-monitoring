"""
agent/tools.py

Database query functions used by agent nodes.
Pure async functions — not LangChain tools (no LLM needed here).

# IMPROVED: Added input validation, configurable thresholds, audit logging
# IMPROVED: Made db_factory explicit parameter for testability
# FIXED: Added timezone-aware datetime handling
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from loguru import logger
from pydantic import BaseModel, Field, field_validator  # FIXED: Pydantic v2 compatibility

# ── Config: Load thresholds from env with validation ──────────
VIOLATION_HISTORY_DAYS = int(os.getenv("AGENT_VIOLATION_HISTORY_DAYS", "7"))
REPEAT_OFFENDER_THRESHOLD = int(os.getenv("AGENT_REPEAT_OFFENDER_THRESHOLD", "3"))
COMPLIANCE_MIN = float(os.getenv("AGENT_COMPLIANCE_MIN", "0"))
COMPLIANCE_MAX = float(os.getenv("AGENT_COMPLIANCE_MAX", "100"))

# ── Pydantic models for structured validation ─────────────────
class ZoneInfo(BaseModel):
    zone_id: str
    zone_name: str
    zone_type: str
    required_ppe: List[str] = Field(default_factory=list)
    
    @field_validator("zone_type")
    @classmethod
    def validate_zone_type(cls, v):
        allowed = {"danger", "caution", "safe", "unknown"}
        return v if v in allowed else "unknown"


class WorkerHistory(BaseModel):
    track_id: int
    days_back: int
    total_violations: int
    unacknowledged: int
    violation_classes: List[str]
    zones: List[str]
    last_violation: Optional[datetime]
    risk_flag: bool
    is_repeat_offender: bool


# ── Protocol for dependency injection (testability) ───────────
@runtime_checkable
class DBFactoryProtocol(Protocol):
    """Protocol for async session factory — enables mocking in tests."""
    def __call__(self): ...


# ── Helper: PII redaction for logs ───────────────────────────
def _redact(value: Any, field: str) -> Any:
    """Redact sensitive fields if PII mode enabled."""
    if os.getenv("REDACT_PII", "false").lower() != "true":
        return value
    if field in {"track_id", "worker_id", "user_id"}:
        return "***REDACTED***"
    return value


# ══════════════════════════════════════════════════════════════
# TOOL 1 — get_worker_violation_history
# ══════════════════════════════════════════════════════════════

async def get_worker_violation_history(
    track_id: int,
    db_factory: DBFactoryProtocol,
    days_back: int = VIOLATION_HISTORY_DAYS,
) -> WorkerHistory:
    """
    Fetch violation history for a worker track_id.
    
    # FIXED: Added input validation for track_id
    # IMPROVED: Return Pydantic model for type safety
    # IMPROVED: Configurable thresholds via env vars
    """
    from sqlalchemy import text
    
    if not isinstance(track_id, int) or track_id < 0:
        raise ValueError(f"Invalid track_id: {track_id}")
    
    since = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat()

    async with db_factory() as session:
        result = await session.execute(
            text("""
                SELECT
                    COUNT(*)                                                    as total,
                    COUNT(CASE WHEN acknowledged=0 THEN 1 END)                  as unacknowledged,
                    GROUP_CONCAT(DISTINCT class_name)                           as classes,
                    GROUP_CONCAT(DISTINCT zone_id)                              as zones,
                    MAX(timestamp)                                              as last_violation
                FROM violation_events
                WHERE track_id = :track_id
                  AND timestamp >= :since
            """),
            {"track_id": track_id, "since": since}
        )
        row = result.mappings().first()

    total = int(row["total"] or 0)
    last_v_raw = row["last_violation"]
    # FIXED: last_violation may already be a datetime object (SQLAlchemy returns native datetime)
    if isinstance(last_v_raw, datetime):
        last_v = last_v_raw
    elif isinstance(last_v_raw, str):
        last_v = datetime.fromisoformat(last_v_raw)
    else:
        last_v = None
    
    history = WorkerHistory(
        track_id=track_id,
        days_back=days_back,
        total_violations=total,
        unacknowledged=int(row["unacknowledged"] or 0),
        violation_classes=list(row["classes"] or []),
        zones=list(row["zones"] or []),
        last_violation=last_v,
        risk_flag=total >= REPEAT_OFFENDER_THRESHOLD,
        is_repeat_offender=total >= REPEAT_OFFENDER_THRESHOLD,
    )
    
    logger.debug(
        "WorkerHistory fetched | track={} | total={} | repeat={}",
        _redact(track_id, "track_id"), history.total_violations, history.is_repeat_offender,
    )
    return history


# ══════════════════════════════════════════════════════════════
# TOOL 2 — get_zone_info
# ══════════════════════════════════════════════════════════════

async def get_zone_info(
    zone_id: str,
    db_factory: DBFactoryProtocol,
) -> ZoneInfo:
    """
    Fetch zone definition from PostgreSQL.
    
    # FIXED: Validate zone_id format
    # IMPROVED: Return Pydantic model with validated zone_type
    """
    from sqlalchemy import text
    
    if not zone_id or not isinstance(zone_id, str):
        raise ValueError(f"Invalid zone_id: {zone_id}")
    
    async with db_factory() as session:
        result = await session.execute(
            text("""
                SELECT zone_id, zone_name, zone_type, required_ppe
                FROM camera_zones
                WHERE zone_id = :zone_id AND active = 1
            """),
            {"zone_id": zone_id}
        )
        row = result.mappings().first()

    if not row:
        logger.warning("Zone not found | zone_id={}", zone_id)
        return ZoneInfo(
            zone_id=zone_id,
            zone_name="Unknown",
            zone_type="unknown",
            required_ppe=[]
        )

    # FIXED: Guard json.loads — value may already be a list (some DB drivers deserialize JSON)
    raw_ppe = row["required_ppe"]
    if isinstance(raw_ppe, list):
        required_ppe = raw_ppe
    elif isinstance(raw_ppe, str):
        try:
            required_ppe = json.loads(raw_ppe)
        except (json.JSONDecodeError, ValueError):
            required_ppe = []
    else:
        required_ppe = []
    
    return ZoneInfo(
        zone_id=row["zone_id"],
        zone_name=row["zone_name"],
        zone_type=row["zone_type"],  # validated by Pydantic
        required_ppe=required_ppe,
    )


# ══════════════════════════════════════════════════════════════
# TOOL 3 — update_compliance_score
# ══════════════════════════════════════════════════════════════

async def update_compliance_score(
    track_id: int,
    delta: float,
    db_factory: DBFactoryProtocol,
) -> float:
    """
    Update compliance score for a worker.
    Score is clamped to [COMPLIANCE_MIN, COMPLIANCE_MAX].
    
    # FIXED: Use timezone-aware datetime
    # IMPROVED: Log audit trail for compliance changes
    # IMPROVED: Configurable min/max via env
    """
    from sqlalchemy import text

    if not isinstance(track_id, int) or track_id < 0:
        raise ValueError(f"Invalid track_id: {track_id}")
    
    # Clamp delta to prevent extreme swings
    delta = max(-20.0, min(20.0, delta))

    async with db_factory() as session:
        result = await session.execute(
            text("""
                INSERT INTO worker_compliance (track_id, score, updated_at)
                VALUES (
                    :track_id, 
                    GREATEST(:min_score, LEAST(:max_score, :initial_score + :delta)), 
                    NOW()
                )
                ON CONFLICT (track_id) DO UPDATE
                    SET score = GREATEST(:min_score, 
                                LEAST(:max_score, worker_compliance.score + :delta)),
                        updated_at = NOW()
                RETURNING score
            """),
            {
                "track_id": track_id, 
                "delta": delta,
                "initial_score": 100.0,
                "min_score": COMPLIANCE_MIN,
                "max_score": COMPLIANCE_MAX,
            }
        )
        row = result.mappings().first()
        await session.commit()

    new_score = float(row["score"]) if row else max(COMPLIANCE_MIN, min(COMPLIANCE_MAX, 100.0 + delta))
    
    logger.info(
        "Compliance updated | track={} | delta={} | new_score={}",
        _redact(track_id, "track_id"), delta, new_score,
    )
    return new_score


# ══════════════════════════════════════════════════════════════
# TOOL 4 — log_agent_run
# ══════════════════════════════════════════════════════════════

async def log_agent_run(
    run_id: str,
    state: dict,
    db_factory: DBFactoryProtocol,
) -> None:
    """
    Persist agent run summary to PostgreSQL for dashboard display.
    
    # FIXED: Redact PII in trace_steps before storage if enabled
    # IMPROVED: Add retry logic for transient DB errors
    """
    from sqlalchemy import text
    import json
    from tenacity import retry, stop_after_attempt, wait_exponential
    
    # Redact PII in trace if enabled
    trace_steps = state.get("trace_steps", [])
    if state.get("redact_pii", False):
        trace_steps = [
            {**step, "details": {
                k: _redact(v, k) for k, v in step.get("details", {}).items()
            }}
            for step in trace_steps
        ]
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def _persist():
        async with db_factory() as session:
            await session.execute(
                text("""
                    INSERT INTO agent_runs
                    (run_id, track_id, class_name, severity_score,
                     alert_level, report_id, alert_sent,
                     compliance_delta, final_status, trace_steps,
                     error, created_at)
                    VALUES
                    (:run_id, :track_id, :class_name, :severity_score,
                     :alert_level, :report_id, :alert_sent,
                     :compliance_delta, :final_status, :trace_steps,
                     :error, NOW())
                """),
                {
                    "run_id": run_id,
                    "track_id": state.get("violation_event", {}).get("track_id"),
                    "class_name": state.get("violation_event", {}).get("class_name"),
                    "severity_score": state.get("severity_score"),
                    "alert_level": state.get("alert_level"),
                    "report_id": state.get("report_id"),
                    "alert_sent": state.get("alert_sent", False),
                    "compliance_delta": state.get("compliance_delta"),
                    "final_status": state.get("final_status", "COMPLETE"),
                    "trace_steps": json.dumps(trace_steps),
                    "error": state.get("error"),
                }
            )
            await session.commit()
    
    try:
        await _persist()
    except Exception as exc:
        logger.error("Agent run log failed after retries: {}", exc)
        # Don't re-raise — audit logging failure shouldn't break the agent