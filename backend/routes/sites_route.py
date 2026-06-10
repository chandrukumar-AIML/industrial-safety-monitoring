"""
backend/routes/sites_route.py

Multi-Site Management API.

Allows a single deployment to manage multiple physical locations
(warehouses, factories, construction sites) under one account.

Endpoints:
  POST   /sites           — create a new site
  GET    /sites           — list all sites
  GET    /sites/{id}      — get site details + KPIs
  PUT    /sites/{id}      — update site info
  DELETE /sites/{id}      — deactivate site
  GET    /sites/{id}/summary — violations/compliance summary per site

Enterprise use case:
  - Safety managers oversee multiple factory floors
  - Each site has its own cameras, zones, workers
  - Dashboard shows cross-site comparison
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession
from loguru import logger

from ..database import get_session
from ..auth.rbac import Role, require_role

router = APIRouter(prefix="/sites", tags=["sites"])


# ── Models ────────────────────────────────────────────────────

class SiteCreateRequest(BaseModel):
    site_id: str = Field(min_length=2, max_length=50, pattern=r"^[a-z0-9_-]+$")
    site_name: str = Field(min_length=1, max_length=100)
    location: Optional[str] = Field(default=None, max_length=200)
    country: Optional[str] = Field(default=None, max_length=50)
    timezone: str = Field(default="UTC", max_length=50)
    industry_type: Optional[str] = Field(default=None, max_length=50)
    contact_email: Optional[str] = Field(default=None, max_length=200)
    active: bool = True

    @field_validator("site_id")
    @classmethod
    def lowercase_id(cls, v: str) -> str:
        return v.lower()


class SiteOut(BaseModel):
    id: int
    site_id: str
    site_name: str
    location: Optional[str]
    country: Optional[str]
    timezone: str
    industry_type: Optional[str]
    contact_email: Optional[str]
    active: bool
    created_at: str


# ── Endpoints ─────────────────────────────────────────────────

@router.post("", status_code=201, response_model=SiteOut)
async def create_site(
    body: SiteCreateRequest,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_role(Role.ADMIN)),
) -> dict:
    """Register a new physical site/location."""
    # Check for duplicate site_id
    existing = await session.execute(
        text("SELECT id FROM sites WHERE site_id = :site_id"),
        {"site_id": body.site_id},
    )
    if existing.first():
        raise HTTPException(409, f"Site ID '{body.site_id}' already exists")

    result = await session.execute(
        text("""
            INSERT INTO sites
                (site_id, site_name, location, country, timezone,
                 industry_type, contact_email, active)
            VALUES
                (:site_id, :site_name, :location, :country, :timezone,
                 :industry_type, :contact_email, :active)
            RETURNING id, created_at
        """),
        {
            "site_id": body.site_id,
            "site_name": body.site_name,
            "location": body.location,
            "country": body.country,
            "timezone": body.timezone,
            "industry_type": body.industry_type,
            "contact_email": body.contact_email,
            "active": body.active,
        },
    )
    row = result.mappings().first()
    await session.commit()
    logger.info("Site created | site_id={} | name={}", body.site_id, body.site_name)
    return {
        "id": row["id"],
        "site_id": body.site_id,
        "site_name": body.site_name,
        "location": body.location,
        "country": body.country,
        "timezone": body.timezone,
        "industry_type": body.industry_type,
        "contact_email": body.contact_email,
        "active": body.active,
        "created_at": str(row["created_at"]),
    }


@router.get("", response_model=List[SiteOut])
async def list_sites(
    active_only: bool = Query(default=True),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list:
    """List all registered sites."""
    where = "WHERE active = 1" if active_only else ""
    result = await session.execute(
        text(f"""
            SELECT id, site_id, site_name, location, country, timezone,
                   industry_type, contact_email, active, created_at
            FROM sites {where}
            ORDER BY site_name
            LIMIT :limit OFFSET :offset
        """),
        {"limit": limit, "offset": offset},
    )
    return [
        {**dict(r), "created_at": str(r["created_at"])}
        for r in result.mappings().all()
    ]


@router.get("/{site_id_or_int}", response_model=SiteOut)
async def get_site(
    site_id_or_int: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Get site details by site_id (slug) or numeric id."""
    if site_id_or_int.isdigit():
        q = "SELECT * FROM sites WHERE id = :val"
        params = {"val": int(site_id_or_int)}
    else:
        q = "SELECT * FROM sites WHERE site_id = :val"
        params = {"val": site_id_or_int}

    result = await session.execute(text(q), params)
    row = result.mappings().first()
    if not row:
        raise HTTPException(404, "Site not found")
    return {**dict(row), "created_at": str(row["created_at"])}


@router.put("/{site_id}", response_model=SiteOut)
async def update_site(
    site_id: str,
    body: SiteCreateRequest,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_role(Role.MANAGER)),
) -> dict:
    """Update site configuration."""
    result = await session.execute(
        text("""
            UPDATE sites SET
                site_name=:site_name, location=:location, country=:country,
                timezone=:timezone, industry_type=:industry_type,
                contact_email=:contact_email, active=:active
            WHERE site_id=:site_id
            RETURNING id, created_at
        """),
        {
            "site_name": body.site_name,
            "location": body.location,
            "country": body.country,
            "timezone": body.timezone,
            "industry_type": body.industry_type,
            "contact_email": body.contact_email,
            "active": body.active,
            "site_id": site_id,
        },
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(404, "Site not found")
    await session.commit()
    return {
        "id": row["id"],
        "site_id": site_id,
        "site_name": body.site_name,
        "location": body.location,
        "country": body.country,
        "timezone": body.timezone,
        "industry_type": body.industry_type,
        "contact_email": body.contact_email,
        "active": body.active,
        "created_at": str(row["created_at"]),
    }


@router.delete("/{site_id}", status_code=204)
async def deactivate_site(
    site_id: str,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_role(Role.ADMIN)),
):
    """Deactivate a site (soft delete)."""
    result = await session.execute(
        text("UPDATE sites SET active=0 WHERE site_id=:site_id RETURNING id"),
        {"site_id": site_id},
    )
    if not result.first():
        raise HTTPException(404, "Site not found")
    await session.commit()
    logger.info("Site deactivated | site_id={}", site_id)


@router.get("/{site_id}/summary")
async def site_summary(
    site_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Cross-site KPI summary — violations, workers, compliance score.
    Joins violation_events and worker_profiles filtered by site_id.
    """
    # Verify site exists
    site_res = await session.execute(
        text("SELECT site_name FROM sites WHERE site_id=:sid AND active=1"),
        {"sid": site_id},
    )
    site_row = site_res.first()
    if not site_row:
        raise HTTPException(404, "Site not found or inactive")

    # Aggregate violation stats (last 30 days)
    stats = await session.execute(
        text("""
            SELECT
                COUNT(*) AS total_violations,
                COUNT(DISTINCT track_id) AS unique_workers_involved,
                AVG(confidence) AS avg_confidence,
                SUM(CASE WHEN acknowledged=0 THEN 1 ELSE 0 END) AS open_violations
            FROM violation_events
            WHERE site_id = :sid
              AND timestamp >= NOW() - INTERVAL '30 days'
        """),
        {"sid": site_id},
    )
    v_row = stats.mappings().first() or {}

    workers = await session.execute(
        text("""
            SELECT
                COUNT(*) AS total_workers,
                AVG(risk_score) AS avg_risk_score,
                SUM(CASE WHEN risk_level='HIGH' THEN 1 ELSE 0 END) AS high_risk_count
            FROM worker_profiles
            WHERE site_id = :sid AND active=1
        """),
        {"sid": site_id},
    )
    w_row = workers.mappings().first() or {}

    total_v = int(v_row.get("total_violations") or 0)
    open_v = int(v_row.get("open_violations") or 0)
    compliance_score = max(0, round(100 - (total_v * 2), 1))

    return {
        "site_id": site_id,
        "site_name": site_row[0],
        "violations_30d": total_v,
        "open_violations": open_v,
        "unique_workers_involved": int(v_row.get("unique_workers_involved") or 0),
        "avg_confidence": round(float(v_row.get("avg_confidence") or 0), 3),
        "total_workers": int(w_row.get("total_workers") or 0),
        "avg_risk_score": round(float(w_row.get("avg_risk_score") or 0), 1),
        "high_risk_workers": int(w_row.get("high_risk_count") or 0),
        "compliance_score": compliance_score,
    }
