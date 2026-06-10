"""
backend/routes/permit_route.py

Digital Permit-to-Work (PTW) system.

High-risk work in industrial plants requires a digital permit:
  - Hot work (welding, cutting, grinding)
  - Confined space entry
  - Electrical isolation / LOTO
  - Working at height
  - Chemical handling

Flow:
  Worker → Request permit → Supervisor reviews → QR code issued
  → Worker scans QR at zone entry → System validates → Access granted
  → Expired permit triggers alert

Endpoints:
  POST /permits                          → Request new permit
  GET  /permits                          → List permits
  GET  /permits/{permit_id}              → Get permit details
  POST /permits/{permit_id}/approve      → Approve permit
  POST /permits/{permit_id}/cancel       → Cancel permit
  POST /permits/{permit_id}/close        → Close permit (work complete)
  GET  /permits/validate/{permit_id}     → QR validation check (zone entry)
  GET  /permits/expired                  → List expired active permits
"""
import hashlib
import json
import secrets
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession
from loguru import logger

from backend.database import get_session
from backend.middleware.rate_limiter import limiter, LIMIT_DEFAULT

router = APIRouter(prefix="/permits", tags=["permits"])

# Work types that require permits
WORK_TYPES = {
    "hot_work":         {"description": "Welding, cutting, grinding — fire hazard", "risk": "CRITICAL"},
    "confined_space":   {"description": "Tank entry, manhole, enclosed area", "risk": "CRITICAL"},
    "electrical":       {"description": "LOTO, HV work, panel maintenance", "risk": "HIGH"},
    "height_work":      {"description": "Work above 2 metres / scaffolding", "risk": "HIGH"},
    "chemical":         {"description": "Hazardous chemical handling/transfer", "risk": "HIGH"},
    "excavation":       {"description": "Digging, trenching, below-ground work", "risk": "HIGH"},
    "radiation":        {"description": "Radiography, nuclear sources", "risk": "CRITICAL"},
    "cold_work":        {"description": "Non-spark mechanical work", "risk": "MEDIUM"},
    "general":          {"description": "General maintenance permit", "risk": "LOW"},
}


def _generate_permit_id() -> str:
    """Generate a unique permit ID: PTW-YYYYMMDD-XXXXXX"""
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    suffix = secrets.token_hex(3).upper()
    return f"PTW-{date_str}-{suffix}"


def _generate_qr_code(permit_id: str) -> str:
    """Generate a QR code payload (in production, generate an actual QR PNG)."""
    # Hash permit_id for tamper detection
    h = hashlib.sha256(permit_id.encode()).hexdigest()[:12]
    return f"PTW-QR:{permit_id}:{h}"


# ── Request models ────────────────────────────────────────────

class PermitRequest(BaseModel):
    org_id: Optional[str] = Field(default=None, max_length=64)
    site_id: Optional[str] = Field(default=None, max_length=50)
    zone_id: Optional[str] = Field(default=None, max_length=64)
    work_type: str = Field(max_length=50)
    worker_id: Optional[str] = Field(default=None, max_length=64)
    supervisor_id: Optional[str] = Field(default=None, max_length=64)
    valid_from: Optional[str] = Field(default=None, description="ISO datetime")
    valid_until: Optional[str] = Field(default=None, description="ISO datetime")
    risk_assessment: Optional[dict] = Field(default=None, description="Risk assessment JSON")


class ApproveRequest(BaseModel):
    approved_by: str = Field(min_length=1, max_length=100)
    notes: Optional[str] = Field(default=None, max_length=500)
    valid_hours: int = Field(default=8, ge=1, le=72, description="Permit valid for N hours from approval")


# ── Routes ────────────────────────────────────────────────────

@router.post("", status_code=201)
@limiter.limit(LIMIT_DEFAULT)
async def request_permit(
    request: Request,
    body: PermitRequest,
    session: AsyncSession = Depends(get_session),
):
    """Request a new work permit."""
    if body.work_type not in WORK_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown work_type '{body.work_type}'. Valid: {list(WORK_TYPES.keys())}"
        )

    permit_id = _generate_permit_id()

    await session.exec(text("""
        INSERT INTO permits_to_work
            (permit_id, org_id, site_id, zone_id, work_type,
             worker_id, supervisor_id, status, valid_from, valid_until, risk_assessment)
        VALUES
            (:permit_id, :org_id, :site_id, :zone_id, :work_type,
             :worker_id, :supervisor_id, 'pending', :valid_from, :valid_until, :risk_assessment)
    """).bindparams(
        permit_id=permit_id,
        org_id=body.org_id,
        site_id=body.site_id,
        zone_id=body.zone_id,
        work_type=body.work_type,
        worker_id=body.worker_id,
        supervisor_id=body.supervisor_id,
        valid_from=body.valid_from,
        valid_until=body.valid_until,
        risk_assessment=json.dumps(body.risk_assessment) if body.risk_assessment else None,
    ))

    work_info = WORK_TYPES[body.work_type]
    logger.info("Permit requested | id={} | type={} | worker={}", permit_id, body.work_type, body.worker_id)

    return {
        "permit_id": permit_id,
        "status": "pending",
        "work_type": body.work_type,
        "risk_level": work_info["risk"],
        "message": f"Permit submitted. Awaiting supervisor approval.",
    }


@router.get("")
@limiter.limit(LIMIT_DEFAULT)
async def list_permits(
    request: Request,
    status: Optional[str] = None,
    org_id: Optional[str] = None,
    zone_id: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    """List permits with optional filters."""
    conditions = ["1=1"]
    params = {}

    if status:
        conditions.append("status = :status")
        params["status"] = status
    if org_id:
        conditions.append("org_id = :org_id")
        params["org_id"] = org_id
    if zone_id:
        conditions.append("zone_id = :zone_id")
        params["zone_id"] = zone_id

    where = "WHERE " + " AND ".join(conditions)
    query = f"""
        SELECT permit_id, org_id, site_id, zone_id, work_type,
               worker_id, supervisor_id, status, valid_from, valid_until,
               approved_by, approved_at, created_at
        FROM permits_to_work {where}
        ORDER BY created_at DESC LIMIT 200
    """

    result = await session.exec(
        text(query).bindparams(**params) if params else text(query)
    )
    rows = result.fetchall()

    permits = []
    now = datetime.now(timezone.utc)
    for row in rows:
        d = dict(row._mapping)
        # Check if expired
        if d.get("valid_until") and d["status"] == "active":
            try:
                vu = datetime.fromisoformat(str(d["valid_until"]).replace("Z", "+00:00"))
                if vu.tzinfo is None:
                    vu = vu.replace(tzinfo=timezone.utc)
                if vu < now:
                    d["status"] = "expired"
            except (ValueError, TypeError):
                pass
        d["work_type_info"] = WORK_TYPES.get(d["work_type"], {})
        permits.append(d)

    return {"total": len(permits), "permits": permits}


@router.get("/validate/{permit_id}")
@limiter.limit(LIMIT_DEFAULT)
async def validate_permit(
    request: Request,
    permit_id: str,
    zone_id: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    """
    Validate a permit at zone entry (QR scan endpoint).
    Returns allowed/denied with reason.
    """
    result = await session.exec(text("""
        SELECT permit_id, status, zone_id, work_type,
               valid_from, valid_until, worker_id, approved_by
        FROM permits_to_work WHERE permit_id = :permit_id
    """).bindparams(permit_id=permit_id))

    row = result.fetchone()
    if not row:
        return {"allowed": False, "reason": "Permit not found", "permit_id": permit_id}

    d = dict(row._mapping)
    now = datetime.now(timezone.utc)

    # Check status
    if d["status"] != "active":
        return {"allowed": False, "reason": f"Permit status is '{d['status']}' — not active", **d}

    # Check time validity
    if d.get("valid_until"):
        try:
            vu = datetime.fromisoformat(str(d["valid_until"]).replace("Z", "+00:00"))
            if vu.tzinfo is None:
                vu = vu.replace(tzinfo=timezone.utc)
            if vu < now:
                return {"allowed": False, "reason": "Permit has expired", **d}
        except (ValueError, TypeError):
            pass

    if d.get("valid_from"):
        try:
            vf = datetime.fromisoformat(str(d["valid_from"]).replace("Z", "+00:00"))
            if vf.tzinfo is None:
                vf = vf.replace(tzinfo=timezone.utc)
            if vf > now:
                return {"allowed": False, "reason": "Permit is not yet valid", **d}
        except (ValueError, TypeError):
            pass

    # Check zone match
    if zone_id and d.get("zone_id") and d["zone_id"] != zone_id:
        return {
            "allowed": False,
            "reason": f"Permit is for zone '{d['zone_id']}', not '{zone_id}'",
            **d,
        }

    return {"allowed": True, "reason": "Permit valid", **d}


@router.post("/{permit_id}/approve")
@limiter.limit(LIMIT_DEFAULT)
async def approve_permit(
    request: Request,
    permit_id: str,
    body: ApproveRequest,
    session: AsyncSession = Depends(get_session),
):
    """Approve a pending permit."""
    # Check exists and is pending
    result = await session.exec(text(
        "SELECT id, status FROM permits_to_work WHERE permit_id = :permit_id"
    ).bindparams(permit_id=permit_id))
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"Permit '{permit_id}' not found")
    if row.status != "pending":
        raise HTTPException(status_code=400, detail=f"Permit status is '{row.status}' — can only approve 'pending'")

    now = datetime.now(timezone.utc)
    valid_until = now + timedelta(hours=body.valid_hours)
    qr_code = _generate_qr_code(permit_id)

    await session.exec(text("""
        UPDATE permits_to_work
        SET status = 'active',
            approved_by = :approved_by,
            approved_at = CURRENT_TIMESTAMP,
            valid_from = :valid_from,
            valid_until = :valid_until,
            qr_code = :qr_code
        WHERE permit_id = :permit_id
    """).bindparams(
        permit_id=permit_id,
        approved_by=body.approved_by,
        valid_from=now.isoformat(),
        valid_until=valid_until.isoformat(),
        qr_code=qr_code,
    ))

    logger.info("Permit approved | id={} | by={} | valid_until={}", permit_id, body.approved_by, valid_until)
    return {
        "permit_id": permit_id,
        "status": "active",
        "approved_by": body.approved_by,
        "valid_from": now.isoformat(),
        "valid_until": valid_until.isoformat(),
        "qr_code": qr_code,
        "message": f"Permit approved. Valid for {body.valid_hours} hours.",
    }


@router.post("/{permit_id}/cancel")
@limiter.limit(LIMIT_DEFAULT)
async def cancel_permit(
    request: Request,
    permit_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Cancel an active or pending permit."""
    result = await session.exec(text("""
        UPDATE permits_to_work
        SET status = 'cancelled'
        WHERE permit_id = :permit_id AND status IN ('pending', 'active')
    """).bindparams(permit_id=permit_id))

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"Permit '{permit_id}' not found or already closed")

    return {"permit_id": permit_id, "status": "cancelled"}


@router.post("/{permit_id}/close")
@limiter.limit(LIMIT_DEFAULT)
async def close_permit(
    request: Request,
    permit_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Close a permit after work is complete."""
    result = await session.exec(text("""
        UPDATE permits_to_work SET status = 'closed'
        WHERE permit_id = :permit_id AND status = 'active'
    """).bindparams(permit_id=permit_id))

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"Permit '{permit_id}' not found or not active")

    return {"permit_id": permit_id, "status": "closed", "message": "Work permit closed successfully"}


@router.get("/expired/list")
@limiter.limit(LIMIT_DEFAULT)
async def list_expired_permits(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """List permits that are active but have passed valid_until."""
    now = datetime.now(timezone.utc).isoformat()
    result = await session.exec(text("""
        SELECT permit_id, org_id, zone_id, work_type, worker_id,
               valid_until, approved_by
        FROM permits_to_work
        WHERE status = 'active' AND valid_until < :now
        ORDER BY valid_until DESC
        LIMIT 100
    """).bindparams(now=now))

    rows = result.fetchall()
    expired = [dict(row._mapping) for row in rows]

    return {
        "total": len(expired),
        "expired_permits": expired,
        "note": "These permits should be closed or cancelled",
    }
