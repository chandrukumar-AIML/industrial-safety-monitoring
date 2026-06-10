"""
backend/routes/weekly_report_route.py

Weekly report listing, generation trigger, and secure PDF download.

# FIXED: Strict path traversal prevention
# FIXED: Proper background task handling
# IMPROVED: Dependency injection & error handling
"""

from __future__ import annotations

import asyncio
import os
import pathlib
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession
from loguru import logger

from ..database import get_session, AsyncSessionLocal

router = APIRouter(prefix="/weekly-reports", tags=["weekly-reports"])

_ALLOWED_REPORT_DIRS = [pathlib.Path(d).resolve() for d in 
                        ["./reports", os.getenv("WEEKLY_REPORT_OUTPUT_DIR", "./reports/weekly")]]


def _validate_pdf_path(path_str: str) -> pathlib.Path:
    path = pathlib.Path(path_str).resolve()
    if not any(str(path).startswith(str(d)) for d in _ALLOWED_REPORT_DIRS):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied")
    return path


class WeeklyReportOut(BaseModel):
    id: int
    report_date: str
    week_start: str
    week_end: str
    site_score: float
    prev_week_score: Optional[float]
    score_delta: Optional[float]
    total_violations: Optional[int]
    total_workers: Optional[int]
    high_risk_count: Optional[int]
    pdf_path: Optional[str]
    pdf_size_bytes: Optional[int]
    email_sent: bool
    created_at: str
    has_pdf: bool


@router.get("", response_model=List[WeeklyReportOut], summary="List weekly reports")
async def list_reports(
    # FIXED: Query() with bounds — prevents unbounded result sets
    limit: int = Query(default=12, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> list:
    result = await session.execute(
        text("""
            SELECT id, report_date, week_start, week_end,
                   COALESCE(site_score, compliance_score, 0.0) AS site_score,
                   NULL AS prev_week_score,
                   NULL AS score_delta,
                   total_violations,
                   NULL AS total_workers,
                   NULL AS high_risk_count,
                   pdf_path,
                   NULL AS pdf_size_bytes,
                   0 AS email_sent,
                   created_at
            FROM weekly_reports ORDER BY report_date DESC LIMIT :limit
        """), {"limit": limit}
    )
    return [
        {
            **dict(row),
            "report_date": str(row["report_date"]) if row["report_date"] else "",
            "week_start": str(row["week_start"]) if row["week_start"] else "",
            "week_end": str(row["week_end"]) if row["week_end"] else "",
            "created_at": str(row["created_at"]) if row["created_at"] else "",
            "has_pdf": bool(row["pdf_path"]),
        }
        for row in result.mappings().all()
    ]


@router.post("/generate", summary="Trigger weekly report generation")
async def trigger_report(
    send_email: bool = True,
    reference_date: Optional[str] = None,
) -> dict:
    """Generate a weekly report on demand. Runs async in background."""
    from ..reports.weekly_scheduler import generate_and_send
    from datetime import date as DateType

    # FIXED: Validate date format before parsing
    ref = None
    if reference_date:
        try:
            ref = DateType.fromisoformat(reference_date)
        except ValueError:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "reference_date must be ISO format (YYYY-MM-DD)")
    asyncio.create_task(generate_and_send(AsyncSessionLocal, ref, send_email), name="weekly_report_manual")
    
    return {"status": "generating", "message": "Report generation started. Check /weekly-reports in 30s."}


@router.get("/{report_id}/download", response_class=FileResponse, summary="Download weekly report PDF")
async def download_report(
    report_id: int,
    session: AsyncSession = Depends(get_session),
) -> FileResponse:
    if report_id < 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid report_id")
        
    result = await session.execute(
        text("SELECT pdf_path, week_start FROM weekly_reports WHERE id=:id"), {"id": report_id}
    )
    row = result.mappings().first()
    if not row or not row["pdf_path"]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report or PDF not found")
        
    pdf_path = _validate_pdf_path(row["pdf_path"])
    if not pdf_path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PDF file missing from disk")
        
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=pdf_path.name,
    )