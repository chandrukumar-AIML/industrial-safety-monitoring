from __future__ import annotations

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Response, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession
from loguru import logger

from ..database import get_session, AsyncSessionLocal
from ..state import app_state

router = APIRouter(prefix="/zones", tags=["zones"])

_VALID_ZONE_TYPES = {"danger", "restricted", "safe"}
_MIN_POLY_VERTICES = 3
_MAX_POLY_VERTICES = 20


# ───────────────── MODELS ─────────────────

class PolygonPoint(BaseModel):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)


class ZoneCreate(BaseModel):
    zone_id: str = Field(min_length=1, max_length=64)
    zone_name: str = Field(min_length=1, max_length=128)
    zone_type: str
    camera_id: str = "default"
    polygon_norm: List[PolygonPoint]
    required_ppe: List[str] = []
    alert_enabled: bool = True
    dwell_threshold_s: float = Field(default=2.0, ge=0.5, le=60.0)
    color_hex: str = "#ef4444"

    @field_validator("zone_type")
    @classmethod
    def validate_zone_type(cls, v: str) -> str:
        if v not in _VALID_ZONE_TYPES:
            raise ValueError(f"zone_type must be one of {_VALID_ZONE_TYPES}")
        return v

    @field_validator("polygon_norm")
    @classmethod
    def validate_polygon(cls, v):
        if len(v) < _MIN_POLY_VERTICES:
            raise ValueError("Polygon must have at least 3 vertices")
        if len(v) > _MAX_POLY_VERTICES:
            raise ValueError("Polygon too large")
        return v


class ZoneOut(BaseModel):
    id: int
    zone_id: str
    zone_name: str
    zone_type: str
    camera_id: str
    polygon_norm: List[List[float]]
    required_ppe: List[str]
    alert_enabled: bool
    dwell_threshold_s: float
    color_hex: str
    active: bool
    created_at: str


# ✅ FIX: defined BEFORE usage — matches actual zone_alerts table schema
class ZoneAlertOut(BaseModel):
    id: int
    zone_id: str
    zone_name: Optional[str]
    alert_type: Optional[str]
    message: Optional[str]
    severity: str
    acknowledged: bool
    acknowledged_by: Optional[str]
    acknowledged_at: Optional[str]
    created_at: str


# ───────────────── HELPERS ─────────────────

async def _reload_engine_zones() -> None:
    from ..alerts.zone_alert_engine import zone_alert_engine

    try:
        count = await zone_alert_engine.load_zones_from_db(AsyncSessionLocal)
        logger.info("Zone engine reloaded: {} zones", count)
    except Exception:
        raise HTTPException(500, "Zone reload failed")


# ───────────────── ROUTES ─────────────────

@router.get("", response_model=List[ZoneOut])
async def list_zones(
    camera_id: Optional[str] = Query(None, max_length=100),
    # FIXED: Added pagination to prevent unbounded SELECT *
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    # FIXED: Use conditional parameterized query instead of f-string WHERE injection
    if camera_id:
        result = await session.execute(
            text("""
                SELECT * FROM camera_zones
                WHERE active = 1 AND camera_id = :camera_id
                ORDER BY id LIMIT :limit OFFSET :offset
            """),
            {"camera_id": camera_id, "limit": limit, "offset": offset},
        )
    else:
        result = await session.execute(
            text("""
                SELECT * FROM camera_zones
                WHERE active = 1
                ORDER BY id LIMIT :limit OFFSET :offset
            """),
            {"limit": limit, "offset": offset},
        )

    return [
        {
            **dict(row),
            "polygon_norm": (
                json.loads(row["polygon_norm"])
                if isinstance(row["polygon_norm"], str) and row["polygon_norm"]
                else ([[0,0],[1,0],[1,1],[0,1]] if not row["polygon_norm"] else row["polygon_norm"])
            ),
            "required_ppe": (
                json.loads(row["required_ppe"])
                if isinstance(row["required_ppe"], str) and row["required_ppe"]
                else (row["required_ppe"] or [])
            ),
            "created_at": str(row["created_at"]) if row["created_at"] else "",
        }
        for row in result.mappings().all()
    ]


@router.post("", status_code=201, response_model=ZoneOut)
async def create_zone(body: ZoneCreate, session: AsyncSession = Depends(get_session)):
    # FIXED: Complete parameterized INSERT (was broken stub)
    import json as _json
    polygon_json = _json.dumps([[p.x, p.y] for p in body.polygon_norm])
    ppe_json = _json.dumps(body.required_ppe)

    result = await session.execute(
        text("""
            INSERT INTO camera_zones
                (zone_id, zone_name, zone_type, camera_id,
                 polygon_norm, required_ppe,
                 alert_enabled, dwell_threshold_s, color_hex, active)
            VALUES
                (:zone_id, :zone_name, :zone_type, :camera_id,
                 :polygon_norm, :required_ppe,
                 :alert_enabled, :dwell_threshold_s, :color_hex, TRUE)
            RETURNING id, created_at
        """),
        {
            "zone_id": body.zone_id,
            "zone_name": body.zone_name,
            "zone_type": body.zone_type,
            "camera_id": body.camera_id,
            "polygon_norm": polygon_json,
            "required_ppe": ppe_json,
            "alert_enabled": body.alert_enabled,
            "dwell_threshold_s": body.dwell_threshold_s,
            "color_hex": body.color_hex,
        },
    )
    row = result.mappings().first()
    await session.commit()

    await _reload_engine_zones()

    return {
        "id": row["id"],
        "zone_id": body.zone_id,
        "zone_name": body.zone_name,
        "zone_type": body.zone_type,
        "camera_id": body.camera_id,
        "polygon_norm": [[p.x, p.y] for p in body.polygon_norm],
        "required_ppe": body.required_ppe,
        "alert_enabled": body.alert_enabled,
        "dwell_threshold_s": body.dwell_threshold_s,
        "color_hex": body.color_hex,
        "active": True,
        "created_at": str(row["created_at"]),
    }


@router.delete("/{zone_id}", status_code=204)
async def delete_zone(
    zone_id: str,
    session: AsyncSession = Depends(get_session),
) -> Response:

    # FIXED: Wrong table name "zones" → "camera_zones"
    result = await session.execute(
        text("UPDATE camera_zones SET active=0 WHERE zone_id=:id RETURNING id"),
        {"id": zone_id}
    )

    if not result.first():
        raise HTTPException(404, "Zone not found")

    await session.commit()

    return Response(status_code=204)


# ✅ FINAL CLEAN ALERTS ROUTE
@router.get("/alerts", response_model=List[ZoneAlertOut])
async def list_zone_alerts(
    zone_id: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    acknowledged: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
):

    where = []
    params = {"limit": limit}

    if zone_id:
        where.append("zone_id = :zone_id")
        params["zone_id"] = zone_id

    if severity:
        where.append("severity = :severity")
        params["severity"] = severity.upper()

    if acknowledged is not None:
        where.append("acknowledged = :ack")
        params["ack"] = acknowledged

    # FIXED: Build safe parameterized query without f-string SQL injection pattern
    # All filter values go into params dict; only safe literal clause names used
    base_sql = "SELECT * FROM zone_alerts"
    filter_sql = (" WHERE " + " AND ".join(where)) if where else ""
    result = await session.execute(
        text(base_sql + filter_sql + " ORDER BY created_at DESC LIMIT :limit"),
        params,
    )

    return [
        {
            **dict(row),
            "acknowledged": bool(row["acknowledged"]),
            "acknowledged_at": str(row["acknowledged_at"]) if row["acknowledged_at"] else None,
            "created_at": str(row["created_at"]) if row["created_at"] else "",
        }
        for row in result.mappings().all()
    ]


class AcknowledgeOut(BaseModel):
    status: str
    id: int


@router.patch("/alerts/{alert_id}/acknowledge", response_model=AcknowledgeOut)
async def acknowledge_alert(
    alert_id: int,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        text("UPDATE zone_alerts SET acknowledged=1 WHERE id=:id RETURNING id"),
        {"id": alert_id}
    )

    if not result.first():
        raise HTTPException(404, "Alert not found")

    await session.commit()

    return {"status": "acknowledged", "id": alert_id}