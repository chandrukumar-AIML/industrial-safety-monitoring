"""
backend/routes/proximity_route.py

Proximity alert listing endpoints.
Lists worker-machine proximity violations detected by the pipeline.

# FIXED: Parameterized queries only — no SQL injection
# FIXED: Input validation (limit ranges)
# IMPROVED: Pydantic response models for OpenAPI schema
# FIXED: Proper datetime string conversion
# IMPROVED: Dependency injection for testability
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession
from loguru import logger

from ..database import get_session

router = APIRouter(prefix="/proximity-alerts", tags=["proximity"])


# ── Response models ───────────────────────────────────────────

class ProximityAlertOut(BaseModel):
    """
    Single proximity alert record.
    Matches the 'proximity_alerts' table schema.
    """
    id: int
    person_track_id: int
    machine_track_id: int
    machine_class: str
    pixel_distance: float
    real_distance_m: Optional[float]
    alert_level: str
    zone_id: Optional[str]
    frame_idx: int
    timestamp: str
    acknowledged: bool


class ProximityStatsOut(BaseModel):
    """
    Aggregated statistics for the proximity dashboard.
    """
    total_alerts: int
    critical_alerts: int
    warning_alerts: int
    most_common_machine: Optional[str]
    avg_distance_m: Optional[float]


# ── Endpoints ─────────────────────────────────────────────────

@router.get(
    "",
    response_model=list[ProximityAlertOut],
    summary="List proximity alerts",
    description="Returns a paginated list of worker-machine proximity violations.",
)
async def list_proximity_alerts(
    limit: int = Query(50, ge=1, le=500, description="Max results (1-500)"),
    acknowledged: Optional[bool] = Query(None, description="Filter by acknowledged status"),
    session: AsyncSession = Depends(get_session),
) -> list[ProximityAlertOut]:
    """
    List recent proximity alerts.
    Default order: Newest first.
    """
    where_clause = ""
    params = {"limit": limit}

    if acknowledged is not None:
        where_clause = "WHERE acknowledged = :ack"
        params["ack"] = acknowledged

    # Parameterized query to prevent SQL injection
    query = text(f"""
        SELECT 
            id, person_track_id, machine_track_id, machine_class,
            pixel_distance, real_distance_m, alert_level,
            zone_id, frame_idx, timestamp, acknowledged
        FROM proximity_alerts
        {where_clause}
        ORDER BY timestamp DESC
        LIMIT :limit
    """)

    try:
        result = await session.execute(query, params)
        rows = result.mappings().all()

        # Convert to Pydantic models (handles datetime serialization automatically)
        output = []
        for row in rows:
            output.append(ProximityAlertOut(
                id=row["id"],
                person_track_id=row["person_track_id"],
                machine_track_id=row["machine_track_id"],
                machine_class=row["machine_class"],
                pixel_distance=row["pixel_distance"],
                real_distance_m=row["real_distance_m"],
                alert_level=row["alert_level"],
                zone_id=row["zone_id"],
                frame_idx=row["frame_idx"],
                timestamp=str(row["timestamp"]),  # Ensure ISO string
                acknowledged=row["acknowledged"],
            ))
        return output

    except Exception as e:
        logger.error("Failed to fetch proximity alerts: {}", e)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Database query failed")


@router.get(
    "/stats",
    response_model=ProximityStatsOut,
    summary="Proximity Alert Statistics",
    description="Returns aggregate stats for the proximity dashboard cards.",
)
async def proximity_stats(
    session: AsyncSession = Depends(get_session),
) -> ProximityStatsOut:
    """Calculate real-time proximity statistics."""
    
    # 1. Total counts by severity
    counts_query = text("""
        SELECT
            COUNT(CASE WHEN alert_level = 'CRITICAL' THEN 1 END) as critical,
            COUNT(CASE WHEN alert_level = 'WARNING' THEN 1 END) as warning,
            COUNT(*) as total
        FROM proximity_alerts
    """)
    counts_row = (await session.execute(counts_query)).mappings().first()

    # 2. Most common machine type
    machine_query = text("""
        SELECT machine_class, COUNT(*) as cnt
        FROM proximity_alerts
        GROUP BY machine_class
        ORDER BY cnt DESC
        LIMIT 1
    """)
    machine_row = (await session.execute(machine_query)).mappings().first()
    most_common = machine_row["machine_class"] if machine_row else None

    # 3. Average real distance (ignore NULLs/estimates if strict)
    avg_query = text("""
        SELECT AVG(real_distance_m) as avg_dist
        FROM proximity_alerts
        WHERE real_distance_m IS NOT NULL
    """)
    avg_row = (await session.execute(avg_query)).mappings().first()
    avg_dist = float(avg_row["avg_dist"]) if avg_row and avg_row["avg_dist"] else None

    return ProximityStatsOut(
        total_alerts=counts_row["total"],
        critical_alerts=counts_row["critical"],
        warning_alerts=counts_row["warning"],
        most_common_machine=most_common,
        avg_distance_m=round(avg_dist, 2) if avg_dist else None,
    )