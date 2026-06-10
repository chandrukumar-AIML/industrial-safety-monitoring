"""
backend/routes/export_route.py

Data export endpoints — CSV / JSON download for compliance reports,
violations, workers, and compliance scores.

Features:
  - Parameterized date range filters
  - CSV and JSON formats
  - Streaming response for large datasets
  - Path-safe filenames with timestamps
  - No SQL injection (fully parameterized)

Used by: compliance teams, safety managers, external auditors.
"""

from __future__ import annotations

import csv
import io
import json
import os
from datetime import date, datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse, Response
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession
from loguru import logger

from ..database import get_session

router = APIRouter(prefix="/export", tags=["export"])

_MAX_EXPORT_ROWS = int(os.getenv("EXPORT_MAX_ROWS", "50000"))


def _safe_filename(prefix: str, ext: str) -> str:
    """Generate a timestamped, safe filename."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"safety_monitor_{prefix}_{ts}.{ext}"


def _date_range_params(
    start_date: Optional[str],
    end_date: Optional[str],
    default_days: int = 30,
) -> tuple[str, str]:
    """Parse and validate date range. Returns ISO date strings."""
    now = datetime.now(timezone.utc).date()
    if end_date:
        try:
            end = date.fromisoformat(end_date)
        except ValueError:
            raise HTTPException(422, "end_date must be YYYY-MM-DD")
    else:
        end = now

    if start_date:
        try:
            start = date.fromisoformat(start_date)
        except ValueError:
            raise HTTPException(422, "start_date must be YYYY-MM-DD")
    else:
        start = end - timedelta(days=default_days)

    if start > end:
        raise HTTPException(422, "start_date must be before end_date")
    if (end - start).days > 365:
        raise HTTPException(422, "Date range cannot exceed 365 days")

    return start.isoformat(), end.isoformat()


# ── Violations Export ─────────────────────────────────────────

@router.get("/violations.csv", summary="Export violation events as CSV")
async def export_violations_csv(
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    zone_id: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    class_name: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """Download all violations as a CSV file."""
    start, end = _date_range_params(start_date, end_date)

    where = ["timestamp >= :start", "timestamp <= :end"]
    params: dict = {"start": start, "end": end + "T23:59:59", "limit": _MAX_EXPORT_ROWS}

    if zone_id:
        where.append("zone_id = :zone_id")
        params["zone_id"] = zone_id
    if severity:
        where.append("severity_level = :severity")
        params["severity"] = severity.upper()
    if class_name:
        where.append("class_name = :class_name")
        params["class_name"] = class_name

    where_sql = " AND ".join(where)
    result = await session.execute(
        text(f"""
            SELECT id, track_id, class_name, confidence, zone_id,
                   bbox_x1, bbox_y1, bbox_x2, bbox_y2,
                   frame_idx, camera_id, timestamp, acknowledged
            FROM violation_events
            WHERE {where_sql}
            ORDER BY timestamp DESC
            LIMIT :limit
        """),
        params,
    )
    rows = result.mappings().all()

    # Build CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Track ID", "Class", "Confidence", "Zone ID",
        "BBox X1", "BBox Y1", "BBox X2", "BBox Y2",
        "Frame", "Camera", "Timestamp", "Acknowledged"
    ])
    for row in rows:
        writer.writerow([
            row["id"], row["track_id"], row["class_name"],
            round(row["confidence"], 3), row["zone_id"] or "",
            row["bbox_x1"], row["bbox_y1"], row["bbox_x2"], row["bbox_y2"],
            row["frame_idx"], row["camera_id"] or "",
            str(row["timestamp"]), row["acknowledged"],
        ])

    logger.info("Violations CSV exported | rows={} | range={} to {}", len(rows), start, end)

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{_safe_filename("violations", "csv")}"'},
    )


@router.get("/violations.json", summary="Export violation events as JSON")
async def export_violations_json(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    zone_id: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Download all violations as a JSON file."""
    start, end = _date_range_params(start_date, end_date)
    params: dict = {"start": start, "end": end + "T23:59:59", "limit": _MAX_EXPORT_ROWS}
    where = ["timestamp >= :start", "timestamp <= :end"]
    if zone_id:
        where.append("zone_id = :zone_id")
        params["zone_id"] = zone_id

    result = await session.execute(
        text(f"SELECT * FROM violation_events WHERE {' AND '.join(where)} ORDER BY timestamp DESC LIMIT :limit"),
        params,
    )
    rows = [dict(r) for r in result.mappings().all()]
    for r in rows:
        r["timestamp"] = str(r["timestamp"])

    payload = json.dumps({"count": len(rows), "violations": rows}, indent=2, default=str)
    return Response(
        content=payload,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{_safe_filename("violations", "json")}"'},
    )


# ── Workers / Compliance Export ───────────────────────────────

@router.get("/workers.csv", summary="Export worker compliance data as CSV")
async def export_workers_csv(
    risk_level: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """Download worker compliance data as CSV."""
    params: dict = {"limit": _MAX_EXPORT_ROWS}
    where = "WHERE active = 1"
    if risk_level:
        where += " AND risk_level = :risk_level"
        params["risk_level"] = risk_level.upper()

    result = await session.execute(
        text(f"""
            SELECT worker_id, full_name, department, shift, role,
                   risk_score, risk_level, hr_alerted,
                   face_embedding IS NOT NULL as enrolled, created_at
            FROM worker_profiles {where}
            ORDER BY risk_score DESC
            LIMIT :limit
        """),
        params,
    )
    rows = result.mappings().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Worker ID", "Full Name", "Department", "Shift", "Role",
        "Risk Score", "Risk Level", "HR Alerted", "Face Enrolled", "Created At"
    ])
    for row in rows:
        writer.writerow([
            row["worker_id"], row["full_name"], row["department"] or "",
            row["shift"] or "", row["role"] or "",
            round(row["risk_score"], 2), row["risk_level"],
            row["hr_alerted"], row["enrolled"], str(row["created_at"]),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{_safe_filename("workers", "csv")}"'},
    )


# ── Incident Reports Export ───────────────────────────────────

@router.get("/reports.csv", summary="Export incident reports as CSV")
async def export_reports_csv(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """Download incident reports summary as CSV."""
    start, end = _date_range_params(start_date, end_date)
    params: dict = {"start": start, "end": end, "limit": _MAX_EXPORT_ROWS}
    where = ["DATE(created_at) >= :start", "DATE(created_at) <= :end"]
    if severity:
        where.append("severity_level = :severity")
        params["severity"] = severity.upper()

    result = await session.execute(
        text(f"""
            SELECT id, violation_id, track_id, class_name, zone_id,
                   confidence, severity_level, osha_reference,
                   model_used, generation_ms, status, created_at
            FROM incident_reports
            WHERE {' AND '.join(where)}
            ORDER BY created_at DESC
            LIMIT :limit
        """),
        params,
    )
    rows = result.mappings().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Report ID", "Violation ID", "Track ID", "Class", "Zone",
        "Confidence", "Severity", "OSHA Reference",
        "Model Used", "Generation MS", "Status", "Created At"
    ])
    for row in rows:
        writer.writerow([
            row["id"], row["violation_id"], row["track_id"],
            row["class_name"], row["zone_id"] or "",
            round(row["confidence"], 3), row["severity_level"],
            row["osha_reference"] or "", row["model_used"] or "",
            row["generation_ms"] or "", row["status"], str(row["created_at"]),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{_safe_filename("reports", "csv")}"'},
    )


# ── Zone Analytics Export ─────────────────────────────────────

@router.get("/zone-analytics.csv", summary="Export zone violation analytics as CSV")
async def export_zone_analytics_csv(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """Per-zone violation count analytics as CSV."""
    start, end = _date_range_params(start_date, end_date)
    result = await session.execute(
        text("""
            SELECT
                ve.zone_id,
                cz.zone_name,
                cz.zone_type,
                COUNT(*) AS total_violations,
                COUNT(DISTINCT ve.track_id) AS unique_workers,
                AVG(ve.confidence) AS avg_confidence,
                SUM(CASE WHEN ve.acknowledged = 0 THEN 1 ELSE 0 END) AS unacknowledged
            FROM violation_events ve
            LEFT JOIN camera_zones cz ON ve.zone_id = cz.zone_id
            WHERE ve.timestamp >= :start AND ve.timestamp <= :end
            GROUP BY ve.zone_id, cz.zone_name, cz.zone_type
            ORDER BY total_violations DESC
        """),
        {"start": start, "end": end + "T23:59:59"},
    )
    rows = result.mappings().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Zone ID", "Zone Name", "Zone Type",
        "Total Violations", "Unique Workers",
        "Avg Confidence", "Unacknowledged"
    ])
    for row in rows:
        writer.writerow([
            row["zone_id"], row["zone_name"] or "", row["zone_type"] or "",
            row["total_violations"], row["unique_workers"],
            round(row["avg_confidence"], 3), row["unacknowledged"],
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{_safe_filename("zone_analytics", "csv")}"'},
    )
