"""
backend/routes/organizations_route.py

Multi-tenant organization management API.
Enterprise SaaS — one org per client company.

Endpoints:
  POST /organizations                    → Create new org (admin only)
  GET  /organizations                    → List all orgs (admin)
  GET  /organizations/{org_id}           → Get org details
  PATCH /organizations/{org_id}          → Update org
  GET  /organizations/{org_id}/usage     → Usage stats (cameras, sites, users)
  POST /organizations/{org_id}/activate  → Activate trial
  POST /organizations/{org_id}/suspend   → Suspend org
"""
import secrets
import string
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.database import get_session
from backend.middleware.tenant import get_tenant_org_id
from backend.middleware.rate_limiter import limiter, LIMIT_DEFAULT

router = APIRouter(prefix="/organizations", tags=["organizations"])


# ── Request / Response models ─────────────────────────────────

class OrgCreate(BaseModel):
    org_name: str = Field(min_length=2, max_length=200)
    industry_type: Optional[str] = Field(default=None, max_length=50)
    country: str = Field(default="IN", max_length=2)
    plan: str = Field(default="starter", pattern="^(starter|growth|enterprise)$")
    admin_email: Optional[str] = Field(default=None, max_length=200)
    max_cameras: int = Field(default=5, ge=1, le=500)
    max_sites: int = Field(default=1, ge=1, le=100)
    max_users: int = Field(default=10, ge=1, le=1000)


class OrgUpdate(BaseModel):
    org_name: Optional[str] = Field(default=None, max_length=200)
    industry_type: Optional[str] = Field(default=None, max_length=50)
    admin_email: Optional[str] = Field(default=None, max_length=200)
    plan: Optional[str] = Field(default=None, pattern="^(starter|growth|enterprise)$")
    max_cameras: Optional[int] = Field(default=None, ge=1, le=500)
    max_sites: Optional[int] = Field(default=None, ge=1, le=100)
    max_users: Optional[int] = Field(default=None, ge=1, le=1000)


def _generate_org_id(name: str) -> str:
    """Generate a unique org_id from name."""
    slug = "".join(
        c.lower() if c.isalnum() else "-"
        for c in name[:20]
    ).strip("-")
    suffix = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(6))
    return f"{slug}-{suffix}"


# ── Routes ────────────────────────────────────────────────────

@router.post("", status_code=201)
@limiter.limit(LIMIT_DEFAULT)
async def create_organization(
    request: Request,
    body: OrgCreate,
    session: AsyncSession = Depends(get_session),
):
    """Create a new tenant organization."""
    org_id = _generate_org_id(body.org_name)
    trial_ends = datetime.now(timezone.utc) + timedelta(days=14)

    await session.exec(text("""
        INSERT INTO organizations
            (org_id, org_name, industry_type, country, plan, plan_status,
             trial_ends_at, max_cameras, max_sites, max_users, admin_email, active)
        VALUES
            (:org_id, :org_name, :industry_type, :country, :plan, 'trial',
             :trial_ends, :max_cameras, :max_sites, :max_users, :admin_email, 1)
    """).bindparams(
        org_id=org_id,
        org_name=body.org_name,
        industry_type=body.industry_type,
        country=body.country,
        plan=body.plan,
        trial_ends=trial_ends.isoformat(),
        max_cameras=body.max_cameras,
        max_sites=body.max_sites,
        max_users=body.max_users,
        admin_email=body.admin_email,
    ))

    return {
        "org_id": org_id,
        "org_name": body.org_name,
        "plan": body.plan,
        "plan_status": "trial",
        "trial_ends_at": trial_ends.isoformat(),
        "message": f"Organization created. Trial ends {trial_ends.strftime('%Y-%m-%d')}.",
    }


@router.get("")
@limiter.limit(LIMIT_DEFAULT)
async def list_organizations(
    request: Request,
    active_only: bool = True,
    session: AsyncSession = Depends(get_session),
):
    """List all organizations (super-admin endpoint)."""
    where = "WHERE active = 1" if active_only else ""
    result = await session.exec(text(f"""
        SELECT org_id, org_name, industry_type, country, plan, plan_status,
               trial_ends_at, max_cameras, max_sites, max_users, admin_email,
               active, created_at
        FROM organizations {where}
        ORDER BY created_at DESC
        LIMIT 200
    """))
    rows = result.fetchall()
    return {
        "total": len(rows),
        "organizations": [dict(r._mapping) for r in rows],
    }


@router.get("/{org_id}")
@limiter.limit(LIMIT_DEFAULT)
async def get_organization(
    request: Request,
    org_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get details for a specific organization."""
    result = await session.exec(text("""
        SELECT org_id, org_name, industry_type, country, plan, plan_status,
               trial_ends_at, max_cameras, max_sites, max_users, admin_email,
               active, created_at
        FROM organizations WHERE org_id = :org_id
    """).bindparams(org_id=org_id))
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Organization '{org_id}' not found")
    return dict(row._mapping)


@router.patch("/{org_id}")
@limiter.limit(LIMIT_DEFAULT)
async def update_organization(
    request: Request,
    org_id: str,
    body: OrgUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update organization details."""
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    updates["org_id"] = org_id

    result = await session.exec(
        text(f"UPDATE organizations SET {set_clause} WHERE org_id = :org_id").bindparams(**updates)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"Organization '{org_id}' not found")

    return {"org_id": org_id, "updated": list(updates.keys()), "status": "ok"}


@router.get("/{org_id}/usage")
@limiter.limit(LIMIT_DEFAULT)
async def get_org_usage(
    request: Request,
    org_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get current resource usage vs plan limits."""
    # Get limits
    org_result = await session.exec(text("""
        SELECT max_cameras, max_sites, max_users, plan, plan_status
        FROM organizations WHERE org_id = :org_id
    """).bindparams(org_id=org_id))
    org = org_result.fetchone()
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization '{org_id}' not found")

    # Count usage
    cam_count = (await session.exec(
        text("SELECT COUNT(*) FROM camera_registry WHERE 1=1")
    )).scalar() or 0

    site_count = (await session.exec(
        text("SELECT COUNT(*) FROM sites WHERE active = 1")
    )).scalar() or 0

    return {
        "org_id": org_id,
        "plan": org.plan,
        "plan_status": org.plan_status,
        "usage": {
            "cameras": {"used": cam_count, "limit": org.max_cameras},
            "sites":   {"used": site_count, "limit": org.max_sites},
            "users":   {"used": 0, "limit": org.max_users},  # user table TBD
        },
        "utilization_pct": {
            "cameras": round(cam_count / max(org.max_cameras, 1) * 100, 1),
            "sites":   round(site_count / max(org.max_sites, 1) * 100, 1),
        },
    }


@router.post("/{org_id}/suspend")
@limiter.limit(LIMIT_DEFAULT)
async def suspend_organization(
    request: Request,
    org_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Suspend an organization (non-payment, violation)."""
    result = await session.exec(text("""
        UPDATE organizations
        SET plan_status = 'suspended', active = 0
        WHERE org_id = :org_id
    """).bindparams(org_id=org_id))
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"Organization '{org_id}' not found")
    return {"org_id": org_id, "plan_status": "suspended", "message": "Organization suspended"}


@router.post("/{org_id}/activate")
@limiter.limit(LIMIT_DEFAULT)
async def activate_organization(
    request: Request,
    org_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Reactivate a suspended or trial organization."""
    result = await session.exec(text("""
        UPDATE organizations
        SET plan_status = 'active', active = 1
        WHERE org_id = :org_id
    """).bindparams(org_id=org_id))
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"Organization '{org_id}' not found")
    return {"org_id": org_id, "plan_status": "active", "message": "Organization activated"}
