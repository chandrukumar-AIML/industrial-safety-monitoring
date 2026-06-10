"""
backend/routes/pose_hazards.py

Pose hazard listing endpoints.

# FIXED: Added Query() validation bounds to prevent abuse
# FIXED: Added response_model for proper schema docs
# FIXED: Added error handling
"""
from __future__ import annotations

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from ..database import get_session

router = APIRouter(prefix="/pose-hazards", tags=["pose"])


# FIXED: Add explicit response model for OpenAPI docs + validation
class PoseHazardOut(BaseModel):
    id: int
    track_id: int
    hazard_type: str
    severity: str
    confidence: float
    zone_id: Optional[str]
    frame_idx: Optional[int]
    landmark_data: dict
    combined_alert: bool
    timestamp: str


@router.get("", response_model=List[PoseHazardOut])
async def list_pose_hazards(
    # FIXED: Proper Query() bounds — prevents unbounded queries
    limit: int = Query(default=50, ge=1, le=500),
    severity: Optional[str] = Query(default=None, max_length=20),
    session: AsyncSession = Depends(get_session),
) -> list:
    try:
        where = ""
        params: dict = {"limit": limit}
        if severity:
            where = "WHERE severity = :severity"
            params["severity"] = severity.upper()

        result = await session.execute(
            text(f"""
                SELECT id, track_id, hazard_type, severity,
                       confidence, zone_id, frame_idx,
                       landmark_data, combined_alert, timestamp
                FROM pose_hazard_events
                {where}
                ORDER BY timestamp DESC
                LIMIT :limit
            """),
            params,
        )
        return [
            {
                **dict(row),
                "landmark_data": json.loads(row["landmark_data"]) if row["landmark_data"] else {},
                "timestamp": str(row["timestamp"]),
            }
            for row in result.mappings().all()
        ]
    except Exception as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Query failed: {type(exc).__name__}")