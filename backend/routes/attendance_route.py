"""
backend/routes/attendance_route.py

Worker Attendance / Headcount system.

Tracks worker entry/exit from camera feeds or manual check-in.
Real-time headcount per site/zone enables:
  - Muster drill accuracy
  - Overtime alerts
  - Zone occupancy limits
  - Emergency evacuation count

Endpoints:
  POST /attendance/checkin          → Worker check-in (face recognition / manual)
  POST /attendance/checkout         → Worker check-out
  GET  /attendance/headcount        → Real-time headcount per site
  GET  /attendance/today            → Today's attendance list
  GET  /attendance/worker/{worker_id} → Attendance history for a worker
  GET  /attendance/active           → Currently on-site workers
  POST /attendance/muster           → Muster drill — count all on-site
"""
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession
from loguru import logger

from backend.database import get_session
from backend.middleware.rate_limiter import limiter, LIMIT_DEFAULT

router = APIRouter(prefix="/attendance", tags=["attendance"])


# ── Request models ────────────────────────────────────────────

class CheckInRequest(BaseModel):
    worker_id: str = Field(min_length=1, max_length=64)
    org_id: Optional[str] = Field(default=None, max_length=64)
    site_id: Optional[str] = Field(default=None, max_length=50)
    shift_id: Optional[int] = Field(default=None)
    entry_method: str = Field(default="manual", pattern="^(face_recognition|manual|qr)$")
    entry_camera_id: Optional[str] = Field(default=None, max_length=64)


class CheckOutRequest(BaseModel):
    worker_id: str = Field(min_length=1, max_length=64)
    org_id: Optional[str] = Field(default=None, max_length=64)
    exit_camera_id: Optional[str] = Field(default=None, max_length=64)


# ── Routes ────────────────────────────────────────────────────

@router.post("/checkin", status_code=201)
@limiter.limit(LIMIT_DEFAULT)
async def check_in(
    request: Request,
    body: CheckInRequest,
    session: AsyncSession = Depends(get_session),
):
    """Record worker check-in."""
    # Check if already checked in today (no checkout)
    today = datetime.now(timezone.utc).date().isoformat()
    result = await session.exec(text("""
        SELECT id FROM worker_attendance
        WHERE worker_id = :worker_id
          AND check_in >= :today
          AND check_out IS NULL
        LIMIT 1
    """).bindparams(worker_id=body.worker_id, today=today))

    if result.fetchone():
        raise HTTPException(
            status_code=409,
            detail=f"Worker '{body.worker_id}' is already checked in. Use /checkout first."
        )

    now = datetime.now(timezone.utc)
    await session.exec(text("""
        INSERT INTO worker_attendance
            (worker_id, org_id, site_id, shift_id, check_in, entry_method, entry_camera_id)
        VALUES
            (:worker_id, :org_id, :site_id, :shift_id, :check_in, :entry_method, :entry_camera_id)
    """).bindparams(
        worker_id=body.worker_id,
        org_id=body.org_id,
        site_id=body.site_id,
        shift_id=body.shift_id,
        check_in=now.isoformat(),
        entry_method=body.entry_method,
        entry_camera_id=body.entry_camera_id,
    ))

    logger.info("Worker checked in | id={} | method={} | site={}", body.worker_id, body.entry_method, body.site_id)
    return {
        "worker_id": body.worker_id,
        "status": "checked_in",
        "check_in": now.isoformat(),
        "entry_method": body.entry_method,
    }


@router.post("/checkout")
@limiter.limit(LIMIT_DEFAULT)
async def check_out(
    request: Request,
    body: CheckOutRequest,
    session: AsyncSession = Depends(get_session),
):
    """Record worker check-out."""
    today = datetime.now(timezone.utc).date().isoformat()

    # Find open check-in
    result = await session.exec(text("""
        SELECT id, check_in FROM worker_attendance
        WHERE worker_id = :worker_id
          AND check_in >= :today
          AND check_out IS NULL
        ORDER BY check_in DESC LIMIT 1
    """).bindparams(worker_id=body.worker_id, today=today))

    row = result.fetchone()
    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"No active check-in found for worker '{body.worker_id}' today"
        )

    now = datetime.now(timezone.utc)

    # Calculate hours
    try:
        check_in = datetime.fromisoformat(str(row.check_in).replace("Z", "+00:00"))
        if check_in.tzinfo is None:
            check_in = check_in.replace(tzinfo=timezone.utc)
        hours_worked = round((now - check_in).total_seconds() / 3600, 2)
    except (ValueError, TypeError):
        hours_worked = None

    await session.exec(text("""
        UPDATE worker_attendance
        SET check_out = :check_out,
            exit_camera_id = :exit_camera_id
        WHERE id = :id
    """).bindparams(
        id=row.id,
        check_out=now.isoformat(),
        exit_camera_id=body.exit_camera_id,
    ))

    logger.info("Worker checked out | id={} | hours={}", body.worker_id, hours_worked)
    return {
        "worker_id": body.worker_id,
        "status": "checked_out",
        "check_out": now.isoformat(),
        "hours_worked": hours_worked,
    }


@router.get("/headcount")
@limiter.limit(LIMIT_DEFAULT)
async def get_headcount(
    request: Request,
    site_id: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    """Real-time headcount — workers currently on-site (checked in, not checked out)."""
    today = datetime.now(timezone.utc).date().isoformat()

    where = "AND site_id = :site_id" if site_id else ""
    params = {"today": today}
    if site_id:
        params["site_id"] = site_id

    result = await session.exec(text(f"""
        SELECT
            COALESCE(site_id, 'unknown') as site,
            COUNT(*) as on_site
        FROM worker_attendance
        WHERE check_in >= :today AND check_out IS NULL {where}
        GROUP BY site_id
        ORDER BY on_site DESC
    """).bindparams(**params))

    rows = result.fetchall()
    total_on_site = sum(row.on_site for row in rows)

    return {
        "total_on_site": total_on_site,
        "by_site": [dict(row._mapping) for row in rows],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/active")
@limiter.limit(LIMIT_DEFAULT)
async def get_active_workers(
    request: Request,
    site_id: Optional[str] = None,
    org_id: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    """List all workers currently on site (checked in without checkout)."""
    today = datetime.now(timezone.utc).date().isoformat()

    conditions = ["wa.check_in >= :today", "wa.check_out IS NULL"]
    params = {"today": today}

    if site_id:
        conditions.append("wa.site_id = :site_id")
        params["site_id"] = site_id
    if org_id:
        conditions.append("wa.org_id = :org_id")
        params["org_id"] = org_id

    where = "WHERE " + " AND ".join(conditions)

    result = await session.exec(text(f"""
        SELECT wa.worker_id, wa.site_id, wa.check_in,
               wa.entry_method, wa.entry_camera_id,
               wp.full_name, wp.department, wp.shift
        FROM worker_attendance wa
        LEFT JOIN worker_profiles wp ON wp.worker_id = wa.worker_id
        {where}
        ORDER BY wa.check_in DESC
        LIMIT 500
    """).bindparams(**params))

    rows = result.fetchall()
    now = datetime.now(timezone.utc)
    workers = []
    for row in rows:
        d = dict(row._mapping)
        try:
            ci = datetime.fromisoformat(str(d["check_in"]).replace("Z", "+00:00"))
            if ci.tzinfo is None:
                ci = ci.replace(tzinfo=timezone.utc)
            d["hours_on_site"] = round((now - ci).total_seconds() / 3600, 2)
        except (ValueError, TypeError):
            d["hours_on_site"] = None
        workers.append(d)

    return {
        "total": len(workers),
        "workers_on_site": workers,
        "timestamp": now.isoformat(),
    }


@router.get("/today")
@limiter.limit(LIMIT_DEFAULT)
async def get_today_attendance(
    request: Request,
    site_id: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    """Today's full attendance log (all check-ins and check-outs)."""
    today = datetime.now(timezone.utc).date().isoformat()
    params = {"today": today}
    where_extra = ""
    if site_id:
        where_extra = " AND site_id = :site_id"
        params["site_id"] = site_id

    result = await session.exec(text(f"""
        SELECT wa.worker_id, wa.site_id, wa.check_in, wa.check_out,
               wa.entry_method, wa.shift_id,
               wp.full_name, wp.department
        FROM worker_attendance wa
        LEFT JOIN worker_profiles wp ON wp.worker_id = wa.worker_id
        WHERE wa.check_in >= :today {where_extra}
        ORDER BY wa.check_in DESC
        LIMIT 1000
    """).bindparams(**params))

    rows = result.fetchall()

    total_checked_in = len(rows)
    total_checked_out = sum(1 for r in rows if r.check_out is not None)
    total_on_site = total_checked_in - total_checked_out

    return {
        "date": today,
        "total_checked_in": total_checked_in,
        "total_checked_out": total_checked_out,
        "total_on_site": total_on_site,
        "records": [dict(row._mapping) for row in rows],
    }


@router.get("/worker/{worker_id}")
@limiter.limit(LIMIT_DEFAULT)
async def get_worker_attendance(
    request: Request,
    worker_id: str,
    days: int = 30,
    session: AsyncSession = Depends(get_session),
):
    """Get attendance history for a specific worker."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    result = await session.exec(text("""
        SELECT wa.worker_id, wa.site_id, wa.check_in, wa.check_out,
               wa.entry_method, wa.shift_id,
               wp.full_name, wp.department, wp.shift
        FROM worker_attendance wa
        LEFT JOIN worker_profiles wp ON wp.worker_id = wa.worker_id
        WHERE wa.worker_id = :worker_id AND wa.check_in >= :since
        ORDER BY wa.check_in DESC
        LIMIT 200
    """).bindparams(worker_id=worker_id, since=since))

    rows = result.fetchall()

    records = []
    total_hours = 0.0
    for row in rows:
        d = dict(row._mapping)
        if d.get("check_in") and d.get("check_out"):
            try:
                ci = datetime.fromisoformat(str(d["check_in"]).replace("Z", "+00:00"))
                co = datetime.fromisoformat(str(d["check_out"]).replace("Z", "+00:00"))
                if ci.tzinfo is None: ci = ci.replace(tzinfo=timezone.utc)
                if co.tzinfo is None: co = co.replace(tzinfo=timezone.utc)
                hours = round((co - ci).total_seconds() / 3600, 2)
                d["hours_worked"] = hours
                total_hours += hours
            except (ValueError, TypeError):
                d["hours_worked"] = None
        records.append(d)

    return {
        "worker_id": worker_id,
        "period_days": days,
        "total_days_present": len(records),
        "total_hours": round(total_hours, 2),
        "records": records,
    }


@router.post("/muster")
@limiter.limit(LIMIT_DEFAULT)
async def muster_drill(
    request: Request,
    site_id: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    """
    Muster drill — snapshot of all workers currently on site.
    Used during emergency evacuations to verify headcount.
    """
    today = datetime.now(timezone.utc).date().isoformat()
    params = {"today": today}
    where_extra = ""
    if site_id:
        where_extra = " AND wa.site_id = :site_id"
        params["site_id"] = site_id

    result = await session.exec(text(f"""
        SELECT wa.worker_id, wa.site_id, wa.check_in, wa.entry_method,
               wp.full_name, wp.department, wp.shift
        FROM worker_attendance wa
        LEFT JOIN worker_profiles wp ON wp.worker_id = wa.worker_id
        WHERE wa.check_in >= :today AND wa.check_out IS NULL {where_extra}
        ORDER BY wa.site_id, wa.check_in
    """).bindparams(**params))

    rows = result.fetchall()
    workers = [dict(row._mapping) for row in rows]

    logger.info("Muster drill | site={} | on_site={}", site_id or "all", len(workers))

    return {
        "muster_time": datetime.now(timezone.utc).isoformat(),
        "site_id": site_id or "all_sites",
        "total_on_site": len(workers),
        "workers": workers,
        "status": "MUSTER_COMPLETE",
        "message": f"{len(workers)} workers accounted for",
    }
