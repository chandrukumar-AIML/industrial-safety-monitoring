"""
backend/routes/detections.py

Violation listing, live detection fallback, and acknowledgment endpoints.

# FIXED: Proper pagination & filtering
# FIXED: Idempotent acknowledgment
# IMPROVED: SQLite-compatible sequential queries (avoid concurrent session locks)
# IMPROVED: Dependency injection for testability
# FIXED: No PII leakage in logs
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, HTTPException, Path, status
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from loguru import logger
from pydantic import BaseModel, Field

from ..database import get_session
from ..models import ViolationEvent, ViolationEventOut, ViolationAcknowledge, DetectionOut
from ..state import app_state

router = APIRouter(prefix="/detections", tags=["detections"])

# ── Typed response models ─────────────────────────────────────
class AcknowledgeResponse(BaseModel):
    status: str = Field(description="Always 'acknowledged'")
    id: int = Field(description="Violation event ID")
    already_existed: bool = Field(description="True if already acknowledged")


class ViolationStatsOut(BaseModel):
    total_violations: int = Field(ge=0)
    unacknowledged: int = Field(ge=0)
    by_class: dict[str, int] = Field(description="Violation count per class")
    by_zone: dict[str, int] = Field(description="Violation count per zone")


# ── Endpoints ─────────────────────────────────────────────────
@router.get(
    "",
    response_model=List[ViolationEventOut],
    summary="List violation events",
)
async def list_violations(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    zone_id: Optional[str] = Query(None, max_length=100),
    class_name: Optional[str] = Query(None, max_length=100),
    acknowledged: Optional[bool] = Query(None, description="Filter by status"),
    session: AsyncSession = Depends(get_session),
) -> List[ViolationEvent]:
    stmt = select(ViolationEvent).order_by(ViolationEvent.timestamp.desc())
    if zone_id:
        stmt = stmt.where(ViolationEvent.zone_id == zone_id)
    if class_name:
        stmt = stmt.where(ViolationEvent.class_name == class_name)
    if acknowledged is not None:
        stmt = stmt.where(ViolationEvent.acknowledged == acknowledged)

    stmt = stmt.offset(offset).limit(limit)
    result = await session.exec(stmt)
    return result.all()


@router.get(
    "/live",
    response_model=List[DetectionOut],
    responses={204: {"description": "No frame processed yet"}},
    summary="Live detections",
)
async def live_detections() -> List[DetectionOut]:
    frame = app_state.get_latest_frame()
    if frame is None:
        return []
    return [
        DetectionOut(
            track_id=d.track_id,
            class_name=d.class_name,
            confidence=round(d.confidence, 3),
            bbox_xyxy=tuple(round(v, 1) for v in d.bbox_xyxy),
            zone_id=d.zone_id,
            is_violation=d.is_violation,
            frame_idx=d.frame_idx,
        )
        for d in frame.detections
    ]


@router.patch(
    "/{violation_id}/acknowledge",
    response_model=AcknowledgeResponse,
    summary="Acknowledge a violation",
)
async def acknowledge_violation(
    violation_id: int = Path(ge=1),
    body: ViolationAcknowledge = ...,
    session: AsyncSession = Depends(get_session),
) -> AcknowledgeResponse:
    event = await session.get(ViolationEvent, violation_id)
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Violation not found")

    already_existed = event.acknowledged
    event.acknowledged = True
    if body.notes is not None:
        event.notes = body.notes
    session.add(event)
    await session.commit()

    return AcknowledgeResponse(
        status="acknowledged",
        id=violation_id,
        already_existed=already_existed,
    )


@router.get(
    "/stats",
    response_model=ViolationStatsOut,
    summary="Violation statistics",
)
async def violation_stats(
    session: AsyncSession = Depends(get_session),
) -> ViolationStatsOut:
    # Sequential queries to avoid SQLite locking issues
    total_res = await session.exec(select(func.count(ViolationEvent.id)))
    unack_res = await session.exec(
        select(func.count(ViolationEvent.id)).where(ViolationEvent.acknowledged.is_(False))
    )
    class_res = await session.exec(
        select(ViolationEvent.class_name, func.count(ViolationEvent.id).label("count"))
        .group_by(ViolationEvent.class_name)
    )
    zone_res = await session.exec(
        select(ViolationEvent.zone_id, func.count(ViolationEvent.id).label("count"))
        .where(ViolationEvent.zone_id.isnot(None))
        .group_by(ViolationEvent.zone_id)
    )

    return ViolationStatsOut(
        total_violations=total_res.one(),
        unacknowledged=unack_res.one(),
        by_class={r[0]: r[1] for r in class_res.all()},
        by_zone={r[0]: r[1] for r in zone_res.all()},
    )
