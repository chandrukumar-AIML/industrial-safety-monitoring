"""
backend/routes/reports_route.py

Incident report listing, details, and secure PDF download.

# FIXED: Strict path traversal prevention for PDF downloads
# FIXED: Proper pagination & filtering
# IMPROVED: Secure file serving with validation
"""

from __future__ import annotations

import os
import pathlib
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession
from loguru import logger

from ..database import get_session

router = APIRouter(prefix="/reports", tags=["reports"])


class ReportOut(BaseModel):
    id: int
    violation_id: Optional[int]
    track_id: int
    class_name: str
    zone_id: Optional[str]
    confidence: float
    timestamp: str
    incident_summary: Optional[str]
    root_cause_analysis: Optional[str]
    corrective_actions: Optional[str]
    osha_reference: Optional[str]
    severity_level: str
    model_used: Optional[str]
    generation_ms: Optional[int]
    pdf_path: Optional[str]
    pdf_size_bytes: Optional[int]
    has_pdf: bool
    status: str
    created_at: str


class ReportSummary(BaseModel):
    total_reports: int
    by_severity: dict[str, int]
    by_class: dict[str, int]
    avg_generation_ms: float


_ALLOWED_REPORT_DIRS = [pathlib.Path(d).resolve() for d in 
                        ["./reports", os.getenv("REPORT_OUTPUT_DIR", "./reports/output")]]


def _validate_pdf_path(path_str: str) -> pathlib.Path:
    path = pathlib.Path(path_str).resolve()
    if not any(str(path).startswith(str(d)) for d in _ALLOWED_REPORT_DIRS):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied: path outside allowed directory")
    return path


@router.get("", response_model=List[ReportOut], summary="List incident reports")
async def list_reports(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    severity: Optional[str] = Query(None),
    class_name: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
) -> list:
    where_clauses = []
    params = {"limit": limit, "offset": offset}
    if severity:
        where_clauses.append("severity_level = :severity")
        params["severity"] = severity.upper()
    if class_name:
        where_clauses.append("class_name = :class_name")
        params["class_name"] = class_name

    where = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    result = await session.execute(
        text(f"""
            SELECT id, violation_id, track_id, class_name, zone_id,
                   confidence, timestamp, incident_summary, root_cause_analysis,
                   corrective_actions, osha_reference, severity_level,
                   model_used, generation_ms, pdf_path, pdf_size_bytes, status, created_at
            FROM incident_reports {where}
            ORDER BY created_at DESC LIMIT :limit OFFSET :offset
        """), params
    )
    return [
        {
            **dict(row),
            "timestamp": str(row["timestamp"]),
            "created_at": str(row["created_at"]),
            "has_pdf": bool(row["pdf_path"]),
        }
        for row in result.mappings().all()
    ]


@router.get("/{report_id}", response_model=ReportOut, summary="Get single incident report")
async def get_report(report_id: int, session: AsyncSession = Depends(get_session)):
    if report_id < 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid report_id")
    result = await session.execute(
        text("SELECT * FROM incident_reports WHERE id = :id"), {"id": report_id}
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")
    return {
        **dict(row),
        "timestamp": str(row["timestamp"]),
        "created_at": str(row["created_at"]),
        "has_pdf": bool(row["pdf_path"]),
    }


@router.get("/{report_id}/download", response_class=FileResponse, summary="Download incident report PDF")
async def download_report(report_id: int, session: AsyncSession = Depends(get_session)) -> FileResponse:
    result = await session.execute(
        text("SELECT pdf_path FROM incident_reports WHERE id = :id"), {"id": report_id}
    )
    row = result.mappings().first()
    if not row or not row["pdf_path"]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report or PDF not found")

    pdf_path = _validate_pdf_path(row["pdf_path"])
    if not pdf_path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PDF file missing from disk")

    return FileResponse(path=str(pdf_path), media_type="application/pdf", filename=pdf_path.name)


@router.get("/stats/summary", response_model=ReportSummary, summary="Report statistics")
async def report_stats(session: AsyncSession = Depends(get_session)) -> ReportSummary:
    total = (await session.execute(text("SELECT COUNT(*) FROM incident_reports"))).scalar() or 0
    sev_rows = (await session.execute(text("SELECT severity_level, COUNT(*) FROM incident_reports GROUP BY severity_level"))).all()
    sev = {r[0]: r[1] for r in sev_rows if r[0]}
    cls_rows = (await session.execute(text("SELECT class_name, COUNT(*) FROM incident_reports GROUP BY class_name"))).all()
    cls = {r[0]: r[1] for r in cls_rows if r[0]}
    avg = float((await session.execute(text("SELECT AVG(generation_ms) FROM incident_reports WHERE generation_ms IS NOT NULL"))).scalar() or 0)

    return ReportSummary(total_reports=total, by_severity=sev, by_class=cls, avg_generation_ms=round(avg, 1))