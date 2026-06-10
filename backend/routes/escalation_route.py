"""
backend/routes/escalation_route.py

Alert Escalation Matrix — L1 → L4

Violation detected → L1 (Supervisor notified, 2-min window)
If not acknowledged → L2 (Safety Officer, 10 min)
If not acknowledged → L3 (Plant Head / Manager, 30 min)
If not acknowledged → L4 (Emergency Response, 0 min — immediate)

APScheduler checks every 60 seconds for overdue escalations.
Notifications sent via: email → WhatsApp → SMS (per configured channels)

Endpoints:
  GET  /escalation/open              → All open/escalated alerts
  GET  /escalation/{violation_id}    → Escalation status for a violation
  POST /escalation/acknowledge/{id}  → Acknowledge an alert
  GET  /escalation/stats             → Escalation statistics
  POST /escalation/trigger/{violation_id} → Manual trigger (for testing)
"""
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession
from loguru import logger

from backend.database import get_session
from backend.middleware.rate_limiter import limiter, LIMIT_DEFAULT

router = APIRouter(prefix="/escalation", tags=["escalation"])


# ── Escalation config ─────────────────────────────────────────

ESCALATION_LEVELS = {
    1: {
        "name": "Supervisor",
        "timeout_minutes": 2,
        "notification_channel": "email",
        "description": "Site supervisor must acknowledge within 2 minutes",
    },
    2: {
        "name": "Safety Officer",
        "timeout_minutes": 10,
        "notification_channel": "email+sms",
        "description": "Safety officer notified — 10 minute window",
    },
    3: {
        "name": "Plant Head",
        "timeout_minutes": 30,
        "notification_channel": "email+sms+call",
        "description": "Plant head / area manager — 30 minute window",
    },
    4: {
        "name": "Emergency Response",
        "timeout_minutes": 0,   # Immediate — no wait window
        "notification_channel": "all",
        "description": "Emergency — all channels, immediate response required",
    },
}


# ── Request models ────────────────────────────────────────────

class AcknowledgeRequest(BaseModel):
    acknowledged_by: str = Field(min_length=1, max_length=100)
    notes: Optional[str] = Field(default=None, max_length=500)


# ── Escalation trigger (called by background scheduler) ───────

async def trigger_escalation(
    violation_id: int,
    org_id: Optional[str],
    site_id: Optional[str],
    session: AsyncSession,
) -> dict:
    """
    Create L1 escalation for a new violation.
    Called automatically when a violation is detected.
    """
    # Check if escalation already exists
    result = await session.exec(text("""
        SELECT id, level, status FROM alert_escalations
        WHERE violation_id = :violation_id AND status IN ('open', 'escalated')
        ORDER BY level DESC LIMIT 1
    """).bindparams(violation_id=violation_id))
    existing = result.fetchone()

    if existing:
        return {"status": "already_exists", "level": existing.level, "id": existing.id}

    # Create L1 escalation
    await session.exec(text("""
        INSERT INTO alert_escalations
            (violation_id, org_id, site_id, level, status, notified_at)
        VALUES
            (:violation_id, :org_id, :site_id, 1, 'open', CURRENT_TIMESTAMP)
    """).bindparams(
        violation_id=violation_id,
        org_id=org_id,
        site_id=site_id,
    ))

    logger.info(
        "Escalation L1 created | violation_id={} | org_id={}",
        violation_id, org_id
    )
    return {"status": "created", "level": 1}


async def run_escalation_check(session: AsyncSession) -> dict:
    """
    Background task — check for overdue escalations and escalate.
    Should be called every 60 seconds by APScheduler.
    """
    now = datetime.now(timezone.utc)
    escalated_count = 0
    closed_count = 0

    # Get all open escalations
    result = await session.exec(text("""
        SELECT ae.id, ae.violation_id, ae.org_id, ae.level, ae.notified_at
        FROM alert_escalations ae
        WHERE ae.status = 'open'
        ORDER BY ae.notified_at ASC
        LIMIT 100
    """))
    open_alerts = result.fetchall()

    for alert in open_alerts:
        current_level = alert.level
        if current_level >= 4:
            continue  # Already at max level

        level_config = ESCALATION_LEVELS.get(current_level, {})
        timeout_mins = level_config.get("timeout_minutes", 5)

        if timeout_mins == 0:
            continue  # Immediate level, no timeout

        # Parse notified_at
        try:
            notified = datetime.fromisoformat(str(alert.notified_at).replace("Z", "+00:00"))
            if notified.tzinfo is None:
                notified = notified.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue

        elapsed_minutes = (now - notified).total_seconds() / 60

        if elapsed_minutes >= timeout_mins:
            next_level = current_level + 1
            next_config = ESCALATION_LEVELS.get(next_level, {})

            # Mark current as escalated, create next level
            await session.exec(text("""
                UPDATE alert_escalations
                SET status = 'escalated',
                    escalation_reason = :reason
                WHERE id = :id
            """).bindparams(
                id=alert.id,
                reason=f"No response in {timeout_mins} minutes — escalated to L{next_level}",
            ))

            await session.exec(text("""
                INSERT INTO alert_escalations
                    (violation_id, org_id, level, status, notified_at)
                VALUES
                    (:violation_id, :org_id, :next_level, 'open', CURRENT_TIMESTAMP)
            """).bindparams(
                violation_id=alert.violation_id,
                org_id=alert.org_id,
                next_level=next_level,
            ))

            logger.warning(
                "Alert escalated | violation={} | L{} → L{} | {} ({})",
                alert.violation_id, current_level, next_level,
                next_config.get("name", "Unknown"),
                next_config.get("notification_channel", "?"),
            )
            escalated_count += 1

    return {
        "checked": len(open_alerts),
        "escalated": escalated_count,
        "closed": closed_count,
        "timestamp": now.isoformat(),
    }


# ── Routes ────────────────────────────────────────────────────

@router.get("/open")
@limiter.limit(LIMIT_DEFAULT)
async def get_open_escalations(
    request: Request,
    org_id: Optional[str] = None,
    level: Optional[int] = None,
    session: AsyncSession = Depends(get_session),
):
    """Get all open/escalated alerts."""
    conditions = ["ae.status IN ('open', 'escalated')"]
    params = {}

    if org_id:
        conditions.append("ae.org_id = :org_id")
        params["org_id"] = org_id
    if level:
        conditions.append("ae.level = :level")
        params["level"] = level

    where = "WHERE " + " AND ".join(conditions)

    result = await session.exec(text(f"""
        SELECT ae.id, ae.violation_id, ae.org_id, ae.site_id,
               ae.level, ae.status, ae.notified_at, ae.escalation_reason,
               ve.class_name, ve.zone_id, ve.confidence, ve.timestamp as violation_ts
        FROM alert_escalations ae
        LEFT JOIN violation_events ve ON ve.id = ae.violation_id
        {where}
        ORDER BY ae.level DESC, ae.notified_at ASC
        LIMIT 200
    """).bindparams(**params) if params else text(f"""
        SELECT ae.id, ae.violation_id, ae.org_id, ae.site_id,
               ae.level, ae.status, ae.notified_at, ae.escalation_reason,
               ve.class_name, ve.zone_id, ve.confidence, ve.timestamp as violation_ts
        FROM alert_escalations ae
        LEFT JOIN violation_events ve ON ve.id = ae.violation_id
        {where}
        ORDER BY ae.level DESC, ae.notified_at ASC
        LIMIT 200
    """))

    rows = result.fetchall()
    alerts = []
    now = datetime.now(timezone.utc)

    for row in rows:
        d = dict(row._mapping)
        # Add level metadata
        level_info = ESCALATION_LEVELS.get(d["level"], {})
        d["level_name"] = level_info.get("name", "Unknown")
        d["notification_channel"] = level_info.get("notification_channel", "")
        # Calculate time overdue
        if d.get("notified_at"):
            try:
                notified = datetime.fromisoformat(str(d["notified_at"]).replace("Z", "+00:00"))
                if notified.tzinfo is None:
                    notified = notified.replace(tzinfo=timezone.utc)
                d["minutes_open"] = round((now - notified).total_seconds() / 60, 1)
            except (ValueError, TypeError):
                d["minutes_open"] = None
        alerts.append(d)

    return {
        "total": len(alerts),
        "critical": sum(1 for a in alerts if a["level"] >= 3),
        "alerts": alerts,
        "escalation_levels": ESCALATION_LEVELS,
    }


@router.get("/{violation_id}")
@limiter.limit(LIMIT_DEFAULT)
async def get_escalation_status(
    request: Request,
    violation_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get full escalation history for a violation."""
    result = await session.exec(text("""
        SELECT ae.id, ae.level, ae.status, ae.notified_at,
               ae.acknowledged_by, ae.acknowledged_at, ae.escalation_reason
        FROM alert_escalations ae
        WHERE ae.violation_id = :violation_id
        ORDER BY ae.level ASC
    """).bindparams(violation_id=violation_id))

    rows = result.fetchall()
    history = []
    for row in rows:
        d = dict(row._mapping)
        level_info = ESCALATION_LEVELS.get(d["level"], {})
        d["level_name"] = level_info.get("name", "Unknown")
        history.append(d)

    if not history:
        raise HTTPException(
            status_code=404,
            detail=f"No escalation found for violation {violation_id}"
        )

    current = max(history, key=lambda x: x["level"])
    return {
        "violation_id": violation_id,
        "current_level": current["level"],
        "current_level_name": current["level_name"],
        "current_status": current["status"],
        "history": history,
    }


@router.post("/acknowledge/{escalation_id}")
@limiter.limit(LIMIT_DEFAULT)
async def acknowledge_escalation(
    request: Request,
    escalation_id: int,
    body: AcknowledgeRequest,
    session: AsyncSession = Depends(get_session),
):
    """Acknowledge an escalation alert."""
    result = await session.exec(text("""
        UPDATE alert_escalations
        SET status = 'acknowledged',
            acknowledged_by = :acknowledged_by,
            acknowledged_at = CURRENT_TIMESTAMP
        WHERE id = :id AND status = 'open'
    """).bindparams(id=escalation_id, acknowledged_by=body.acknowledged_by))

    if result.rowcount == 0:
        raise HTTPException(
            status_code=404,
            detail=f"Escalation {escalation_id} not found or already acknowledged"
        )

    logger.info("Alert acknowledged | id={} | by={}", escalation_id, body.acknowledged_by)
    return {
        "escalation_id": escalation_id,
        "status": "acknowledged",
        "acknowledged_by": body.acknowledged_by,
        "acknowledged_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/trigger/{violation_id}", status_code=201)
@limiter.limit(LIMIT_DEFAULT)
async def manual_trigger(
    request: Request,
    violation_id: int,
    org_id: Optional[str] = None,
    site_id: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    """Manually trigger escalation for a violation (testing / force-escalate)."""
    result = await trigger_escalation(violation_id, org_id, site_id, session)
    return result


@router.get("/stats/summary")
@limiter.limit(LIMIT_DEFAULT)
async def escalation_stats(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Get escalation statistics for the dashboard."""
    result = await session.exec(text("""
        SELECT
            level,
            status,
            COUNT(*) as count
        FROM alert_escalations
        GROUP BY level, status
        ORDER BY level, status
    """))
    rows = result.fetchall()

    stats: dict = {
        "by_level": {},
        "by_status": {},
        "total": 0,
    }
    for row in rows:
        d = dict(row._mapping)
        level = str(d["level"])
        status = d["status"]
        count = d["count"]

        if level not in stats["by_level"]:
            stats["by_level"][level] = {}
        stats["by_level"][level][status] = count

        stats["by_status"][status] = stats["by_status"].get(status, 0) + count
        stats["total"] += count

    return stats
