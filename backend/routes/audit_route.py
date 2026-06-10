"""
backend/routes/audit_route.py

Audit Log API — immutable record of every significant action.

Tracks:
  - Violation acknowledgements (who, when, notes)
  - Worker profile changes (enroll, update, delete)
  - Webhook creates/deletes/tests
  - API key creates/revocations
  - Zone configuration changes
  - System config changes

Endpoints:
  GET  /audit                — paginated audit log
  GET  /audit/stats          — counts by action type
  POST /audit                — (internal) write an audit entry

Enterprise compliance: OSHA, ISO 45001 require audit trails
for all safety-related decisions.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession
from loguru import logger

from ..database import get_session
from ..auth.rbac import Role, require_role

router = APIRouter(prefix="/audit", tags=["audit"])

_VALID_ACTIONS = [
    "violation.acknowledged",
    "violation.unacknowledged",
    "worker.created",
    "worker.updated",
    "worker.deleted",
    "worker.face_enrolled",
    "webhook.created",
    "webhook.deleted",
    "webhook.tested",
    "apikey.created",
    "apikey.revoked",
    "apikey.rotated",
    "zone.created",
    "zone.updated",
    "zone.deleted",
    "shift.created",
    "shift.updated",
    "site.created",
    "site.deactivated",
    "config.changed",
    "report.generated",
    "export.downloaded",
    "system.startup",
    "system.shutdown",
]


# ── Models ────────────────────────────────────────────────────

class AuditEntryCreate(BaseModel):
    action: str = Field(description="Action type e.g. violation.acknowledged")
    actor: str = Field(default="system", max_length=100,
                       description="Who performed the action (user/api_key name or 'system')")
    resource_type: Optional[str] = Field(default=None, max_length=50,
                                          description="What kind of resource (violation, worker, webhook…)")
    resource_id: Optional[str] = Field(default=None, max_length=100,
                                        description="ID of the resource affected")
    details: Optional[Dict[str, Any]] = Field(default=None,
                                               description="Extra context (old/new values, notes…)")
    ip_address: Optional[str] = Field(default=None, max_length=45)


class AuditEntryOut(BaseModel):
    id: int
    action: str
    actor: str
    resource_type: Optional[str]
    resource_id: Optional[str]
    details: Optional[Any]  # dict from system writes, plain string from seed
    ip_address: Optional[str]
    created_at: str


# ── Internal helper (used by other routes) ───────────────────

async def write_audit(
    session: AsyncSession,
    action: str,
    actor: str = "system",
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
) -> None:
    """Write one audit entry. Call from other route handlers."""
    try:
        await session.execute(
            text("""
                INSERT INTO audit_log
                    (action, actor, resource_type, resource_id, details, ip_address, created_at)
                VALUES
                    (:action, :actor, :resource_type, :resource_id,
                     :details, :ip_address, :created_at)
            """),
            {
                "action": action,
                "actor": actor,
                "resource_type": resource_type,
                "resource_id": str(resource_id) if resource_id else None,
                "details": json.dumps(details, default=str) if details else None,
                "ip_address": ip_address,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception as exc:
        # Never let audit failures break the main operation
        logger.warning("Audit write failed (non-fatal): {}", exc)


# ── Endpoints ─────────────────────────────────────────────────

@router.get("", response_model=List[AuditEntryOut])
async def list_audit_log(
    action: Optional[str] = Query(default=None, description="Filter by action type"),
    actor: Optional[str] = Query(default=None, description="Filter by actor"),
    resource_type: Optional[str] = Query(default=None),
    resource_id: Optional[str] = Query(default=None),
    start_date: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    end_date: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_role(Role.MANAGER)),
) -> list:
    """Paginated, filterable audit log. Requires manager role or above."""
    conditions = []
    params: dict = {"limit": limit, "offset": offset}

    if action:
        conditions.append("action = :action")
        params["action"] = action
    if actor:
        conditions.append("actor LIKE :actor")
        params["actor"] = f"%{actor}%"
    if resource_type:
        conditions.append("resource_type = :resource_type")
        params["resource_type"] = resource_type
    if resource_id:
        conditions.append("resource_id = :resource_id")
        params["resource_id"] = resource_id
    if start_date:
        try:
            datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(422, "start_date must be YYYY-MM-DD")
        conditions.append("created_at >= :start_date")
        params["start_date"] = start_date
    if end_date:
        try:
            datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(422, "end_date must be YYYY-MM-DD")
        conditions.append("created_at <= :end_date")
        params["end_date"] = end_date + "T23:59:59"

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    result = await session.execute(
        text(f"""
            SELECT id, action, actor, resource_type, resource_id,
                   details, ip_address, created_at
            FROM audit_log {where}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """),
        params,
    )
    rows = result.mappings().all()
    return [
        {
            **{k: v for k, v in dict(r).items() if k != "details"},
            "details": (
                json.loads(r["details"])
                if r["details"] and isinstance(r["details"], str) and r["details"].startswith("{")
                else (r["details"] if r["details"] else None)
            ),
            "created_at": str(r["created_at"]),
        }
        for r in rows
    ]


@router.get("/stats")
async def audit_stats(
    days: int = Query(default=30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_role(Role.MANAGER)),
) -> dict:
    """Audit action counts grouped by type (last N days)."""
    result = await session.execute(
        text("""
            SELECT action, COUNT(*) AS count
            FROM audit_log
            WHERE created_at >= datetime('now', '-' || :days || ' days')
            GROUP BY action
            ORDER BY count DESC
        """),
        {"days": days},
    )
    rows = result.mappings().all()
    return {
        "period_days": days,
        "total": sum(r["count"] for r in rows),
        "by_action": {r["action"]: r["count"] for r in rows},
    }


@router.post("", status_code=201)
async def create_audit_entry(
    body: AuditEntryCreate,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_role(Role.ADMIN)),
) -> dict:
    """Manually write an audit entry (admin only — for external system integrations)."""
    await write_audit(
        session,
        action=body.action,
        actor=body.actor,
        resource_type=body.resource_type,
        resource_id=body.resource_id,
        details=body.details,
        ip_address=body.ip_address,
    )
    await session.commit()
    return {"status": "logged", "action": body.action}
