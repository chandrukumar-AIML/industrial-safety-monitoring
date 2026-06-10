"""
backend/routes/shifts_route.py

Shift Management API.

Industrial sites operate in shifts (morning/afternoon/night).
This module tracks shift schedules, assigns workers to shifts,
and aggregates per-shift safety analytics.

Endpoints:
  POST   /shifts              — create shift template
  GET    /shifts              — list all shift templates
  GET    /shifts/active       — get currently active shift
  PUT    /shifts/{id}         — update shift template
  DELETE /shifts/{id}         — delete shift template
  GET    /shifts/{id}/stats   — violations/compliance per shift
  POST   /shifts/assign       — assign workers to a shift
"""

from __future__ import annotations

from datetime import datetime, timezone, time
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession
from loguru import logger

from ..database import get_session
from ..auth.rbac import Role, require_role

router = APIRouter(prefix="/shifts", tags=["shifts"])

_VALID_SHIFT_TYPES = ["morning", "afternoon", "night", "custom"]


# ── Models ────────────────────────────────────────────────────

class ShiftCreateRequest(BaseModel):
    shift_name: str = Field(min_length=1, max_length=100)
    shift_type: str = Field(default="custom")
    start_time: str = Field(description="HH:MM (24h format)", pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(description="HH:MM (24h format)", pattern=r"^\d{2}:\d{2}$")
    site_id: Optional[str] = Field(default=None, max_length=50)
    supervisor_name: Optional[str] = Field(default=None, max_length=100)
    max_workers: int = Field(default=50, ge=1, le=500)
    active: bool = True

    @field_validator("shift_type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in _VALID_SHIFT_TYPES:
            raise ValueError(f"shift_type must be one of: {_VALID_SHIFT_TYPES}")
        return v


class ShiftOut(BaseModel):
    id: int
    shift_name: str
    shift_type: str
    start_time: str
    end_time: str
    site_id: Optional[str]
    supervisor_name: Optional[str]
    max_workers: int
    active: bool
    created_at: str


class ShiftAssignRequest(BaseModel):
    shift_id: int
    worker_ids: List[str] = Field(min_length=1)


# ── Helpers ───────────────────────────────────────────────────

def _is_shift_active(start_str: str, end_str: str) -> bool:
    """Check if shift is currently active based on HH:MM strings."""
    try:
        now = datetime.now(timezone.utc).time().replace(second=0, microsecond=0)
        start = time(*[int(x) for x in start_str.split(":")])
        end = time(*[int(x) for x in end_str.split(":")])
        if start <= end:
            return start <= now <= end
        else:
            # Overnight shift (e.g. 22:00 → 06:00)
            return now >= start or now <= end
    except Exception:
        return False


# ── Endpoints ─────────────────────────────────────────────────

@router.post("", status_code=201, response_model=ShiftOut)
async def create_shift(
    body: ShiftCreateRequest,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_role(Role.MANAGER)),
) -> dict:
    """Create a new shift template."""
    result = await session.execute(
        text("""
            INSERT INTO shifts
                (shift_name, shift_type, start_time, end_time,
                 site_id, supervisor_name, max_workers, active)
            VALUES
                (:shift_name, :shift_type, :start_time, :end_time,
                 :site_id, :supervisor_name, :max_workers, :active)
            RETURNING id, created_at
        """),
        {
            "shift_name": body.shift_name,
            "shift_type": body.shift_type,
            "start_time": body.start_time,
            "end_time": body.end_time,
            "site_id": body.site_id,
            "supervisor_name": body.supervisor_name,
            "max_workers": body.max_workers,
            "active": body.active,
        },
    )
    row = result.mappings().first()
    await session.commit()
    logger.info("Shift created | name={} | {}→{}", body.shift_name, body.start_time, body.end_time)
    return {
        "id": row["id"],
        "shift_name": body.shift_name,
        "shift_type": body.shift_type,
        "start_time": body.start_time,
        "end_time": body.end_time,
        "site_id": body.site_id,
        "supervisor_name": body.supervisor_name,
        "max_workers": body.max_workers,
        "active": body.active,
        "created_at": str(row["created_at"]),
    }


@router.get("", response_model=List[ShiftOut])
async def list_shifts(
    site_id: Optional[str] = Query(default=None),
    active_only: bool = Query(default=True),
    session: AsyncSession = Depends(get_session),
) -> list:
    """List all shift templates, optionally filtered by site."""
    conditions = []
    params: dict = {}

    if active_only:
        conditions.append("active = 1")
    if site_id:
        conditions.append("site_id = :site_id")
        params["site_id"] = site_id

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    result = await session.execute(
        text(f"""
            SELECT id, shift_name, shift_type, start_time, end_time,
                   site_id, supervisor_name, max_workers, active, created_at
            FROM shifts {where}
            ORDER BY start_time
        """),
        params,
    )
    rows = result.mappings().all()
    return [
        {**dict(r), "created_at": str(r["created_at"])}
        for r in rows
    ]


@router.get("/active")
async def get_active_shift(
    site_id: Optional[str] = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Get the currently active shift(s) based on current UTC time."""
    conditions = ["active = 1"]
    params: dict = {}
    if site_id:
        conditions.append("site_id = :site_id")
        params["site_id"] = site_id

    result = await session.execute(
        text(f"SELECT * FROM shifts WHERE {' AND '.join(conditions)} ORDER BY start_time"),
        params,
    )
    all_shifts = result.mappings().all()
    active = [
        {**dict(s), "created_at": str(s["created_at"])}
        for s in all_shifts
        if _is_shift_active(s["start_time"], s["end_time"])
    ]
    return {
        "current_utc": datetime.now(timezone.utc).strftime("%H:%M"),
        "active_shifts": active,
        "count": len(active),
    }


@router.put("/{shift_id}", response_model=ShiftOut)
async def update_shift(
    shift_id: int,
    body: ShiftCreateRequest,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_role(Role.MANAGER)),
) -> dict:
    """Update shift configuration."""
    result = await session.execute(
        text("""
            UPDATE shifts SET
                shift_name=:shift_name, shift_type=:shift_type,
                start_time=:start_time, end_time=:end_time,
                site_id=:site_id, supervisor_name=:supervisor_name,
                max_workers=:max_workers, active=:active
            WHERE id=:id
            RETURNING id, created_at
        """),
        {
            "shift_name": body.shift_name,
            "shift_type": body.shift_type,
            "start_time": body.start_time,
            "end_time": body.end_time,
            "site_id": body.site_id,
            "supervisor_name": body.supervisor_name,
            "max_workers": body.max_workers,
            "active": body.active,
            "id": shift_id,
        },
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(404, "Shift not found")
    await session.commit()
    return {
        "id": row["id"],
        "shift_name": body.shift_name,
        "shift_type": body.shift_type,
        "start_time": body.start_time,
        "end_time": body.end_time,
        "site_id": body.site_id,
        "supervisor_name": body.supervisor_name,
        "max_workers": body.max_workers,
        "active": body.active,
        "created_at": str(row["created_at"]),
    }


@router.delete("/{shift_id}", status_code=204)
async def delete_shift(
    shift_id: int,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_role(Role.MANAGER)),
):
    """Remove a shift template."""
    result = await session.execute(
        text("DELETE FROM shifts WHERE id=:id RETURNING id"),
        {"id": shift_id},
    )
    if not result.first():
        raise HTTPException(404, "Shift not found")
    await session.commit()
    logger.info("Shift deleted | id={}", shift_id)


@router.get("/{shift_id}/stats")
async def shift_stats(
    shift_id: int,
    days: int = Query(default=30, ge=1, le=90),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Per-shift safety analytics over the last N days."""
    shift_res = await session.execute(
        text("SELECT * FROM shifts WHERE id=:id"),
        {"id": shift_id},
    )
    shift = shift_res.mappings().first()
    if not shift:
        raise HTTPException(404, "Shift not found")

    # Violations where worker was assigned to this shift
    stats = await session.execute(
        text("""
            SELECT
                COUNT(*) AS total_violations,
                COUNT(DISTINCT ve.track_id) AS unique_workers,
                AVG(ve.confidence) AS avg_confidence
            FROM violation_events ve
            JOIN shift_assignments sa ON ve.track_id::text = sa.worker_id
            WHERE sa.shift_id = :shift_id
              AND ve.timestamp >= NOW() - (:days * INTERVAL '1 day')
        """),
        {"shift_id": shift_id, "days": days},
    )
    row = stats.mappings().first() or {}

    worker_count = await session.execute(
        text("SELECT COUNT(DISTINCT worker_id) FROM shift_assignments WHERE shift_id=:id"),
        {"id": shift_id},
    )
    wc = worker_count.scalar() or 0

    return {
        "shift_id": shift_id,
        "shift_name": shift["shift_name"],
        "shift_type": shift["shift_type"],
        "hours": f"{shift['start_time']} → {shift['end_time']}",
        "assigned_workers": wc,
        "violations_last_days": days,
        "total_violations": int(row.get("total_violations") or 0),
        "unique_workers_involved": int(row.get("unique_workers") or 0),
        "avg_confidence": round(float(row.get("avg_confidence") or 0), 3),
    }


@router.post("/assign", status_code=201)
async def assign_workers(
    body: ShiftAssignRequest,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_role(Role.MANAGER)),
) -> dict:
    """Assign workers to a shift (upsert)."""
    # Verify shift exists
    shift_res = await session.execute(
        text("SELECT id, shift_name FROM shifts WHERE id=:id AND active=1"),
        {"id": body.shift_id},
    )
    if not shift_res.first():
        raise HTTPException(404, "Shift not found or inactive")

    inserted = 0
    for worker_id in body.worker_ids:
        await session.execute(
            text("""
                INSERT INTO shift_assignments (shift_id, worker_id)
                VALUES (:shift_id, :worker_id)
                ON CONFLICT DO NOTHING
            """),
            {"shift_id": body.shift_id, "worker_id": worker_id},
        )
        inserted += 1

    await session.commit()
    logger.info("Assigned {} workers to shift {}", inserted, body.shift_id)
    return {
        "shift_id": body.shift_id,
        "workers_assigned": inserted,
        "worker_ids": body.worker_ids,
    }
