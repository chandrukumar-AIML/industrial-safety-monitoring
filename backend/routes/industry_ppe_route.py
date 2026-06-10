"""
backend/routes/industry_ppe_route.py

Industry-specific PPE profile management.

Each industry has different required PPE per zone type.
These profiles drive compliance checking — a detection is only a violation
if the missing PPE is REQUIRED for that zone's industry_type.

Pre-seeded industries:
  1. construction        → hard hat, vest, gloves, boots, goggles
  2. steel_manufacturing → hard hat, vest, gloves, boots, goggles, face shield
  3. oil_gas             → hard hat, vest, gloves, boots, FR suit, H2S monitor
  4. pharma              → cleanroom suit, gloves, mask, goggles, hairnet
  5. warehouse           → vest, boots, gloves
  6. power_plant         → hard hat, vest, gloves, boots, arc flash suit
  7. shipbuilding        → hard hat, vest, gloves, boots, harness (heights)
  8. mining              → hard hat, vest, gloves, boots, dust mask, lamp

Endpoints:
  GET  /industry-ppe/profiles           → All profiles
  GET  /industry-ppe/profiles/{industry} → Profiles for one industry
  POST /industry-ppe/seed               → Seed default profiles (idempotent)
  POST /industry-ppe/profiles           → Add custom profile
  GET  /industry-ppe/check              → Check compliance for a detection
"""
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession
from loguru import logger

from backend.database import get_session
from backend.middleware.rate_limiter import limiter, LIMIT_DEFAULT

router = APIRouter(prefix="/industry-ppe", tags=["industry-ppe"])


# ── Seed data ─────────────────────────────────────────────────

INDUSTRY_PPE_SEED = [
    # Construction
    {"industry_type": "construction", "zone_type": "general",
     "required_ppe": ["no hardhat", "no vest", "no boots"],
     "risk_level": "HIGH", "compliance_standard": "IS 2925 / OSHA 1926.100",
     "notes": "Standard construction site PPE"},
    {"industry_type": "construction", "zone_type": "height_work",
     "required_ppe": ["no hardhat", "no vest", "no boots", "no harness"],
     "risk_level": "CRITICAL", "compliance_standard": "OSHA 1926.502",
     "notes": "Fall protection required above 6 feet"},
    {"industry_type": "construction", "zone_type": "welding",
     "required_ppe": ["no hardhat", "no gloves", "no goggles", "no boots"],
     "risk_level": "HIGH", "compliance_standard": "OSHA 1926.102",
     "notes": "Eye and face protection for welding operations"},

    # Steel / Manufacturing
    {"industry_type": "steel_manufacturing", "zone_type": "general",
     "required_ppe": ["no hardhat", "no vest", "no gloves", "no boots"],
     "risk_level": "HIGH", "compliance_standard": "Factories Act 1948 / OSHA 1910.132",
     "notes": "Minimum PPE for steel plant floor"},
    {"industry_type": "steel_manufacturing", "zone_type": "furnace",
     "required_ppe": ["no hardhat", "no gloves", "no goggles", "no boots", "no suit"],
     "risk_level": "CRITICAL", "compliance_standard": "OSHA 1910.269",
     "notes": "Heat-resistant suit and face shield near furnace"},
    {"industry_type": "steel_manufacturing", "zone_type": "grinding",
     "required_ppe": ["no hardhat", "no goggles", "no gloves", "no boots"],
     "risk_level": "HIGH", "compliance_standard": "OSHA 1910.133",
     "notes": "Eye protection mandatory for grinding operations"},

    # Oil & Gas
    {"industry_type": "oil_gas", "zone_type": "general",
     "required_ppe": ["no hardhat", "no vest", "no boots", "no suit"],
     "risk_level": "HIGH", "compliance_standard": "OISD-115 / OSHA 1910.119",
     "notes": "FR (flame-resistant) clothing required on process areas"},
    {"industry_type": "oil_gas", "zone_type": "confined_space",
     "required_ppe": ["no hardhat", "no vest", "no boots", "no mask", "no suit"],
     "risk_level": "CRITICAL", "compliance_standard": "OSHA 1910.146",
     "notes": "SCBA/air-line respirator for confined space entry"},
    {"industry_type": "oil_gas", "zone_type": "flare",
     "required_ppe": ["no hardhat", "no suit", "no goggles", "no boots"],
     "risk_level": "CRITICAL", "compliance_standard": "OISD-189",
     "notes": "Proximity to flare — heat protection mandatory"},

    # Pharma
    {"industry_type": "pharma", "zone_type": "cleanroom",
     "required_ppe": ["no suit", "no gloves", "no mask", "no goggles"],
     "risk_level": "HIGH", "compliance_standard": "WHO GMP / Schedule M",
     "notes": "Full gowning protocol for cleanroom areas"},
    {"industry_type": "pharma", "zone_type": "dispensing",
     "required_ppe": ["no suit", "no gloves", "no mask"],
     "risk_level": "HIGH", "compliance_standard": "WHO GMP",
     "notes": "Chemical dispensing — prevent cross-contamination"},
    {"industry_type": "pharma", "zone_type": "general",
     "required_ppe": ["no mask", "no gloves"],
     "risk_level": "MEDIUM", "compliance_standard": "Factories Act 1948",
     "notes": "Basic hygiene PPE for pharma production areas"},

    # Warehouse / Logistics
    {"industry_type": "warehouse", "zone_type": "general",
     "required_ppe": ["no vest", "no boots"],
     "risk_level": "MEDIUM", "compliance_standard": "OSHA 1910.132",
     "notes": "Visibility vest and safety boots for all warehouse areas"},
    {"industry_type": "warehouse", "zone_type": "loading_dock",
     "required_ppe": ["no vest", "no boots", "no hardhat"],
     "risk_level": "HIGH", "compliance_standard": "OSHA 1910.178",
     "notes": "Hard hat required near forklift operations"},

    # Power Plant
    {"industry_type": "power_plant", "zone_type": "general",
     "required_ppe": ["no hardhat", "no vest", "no boots"],
     "risk_level": "HIGH", "compliance_standard": "CEA Regulations 2010",
     "notes": "Standard PPE for power plant operations"},
    {"industry_type": "power_plant", "zone_type": "switchyard",
     "required_ppe": ["no hardhat", "no suit", "no gloves", "no goggles", "no boots"],
     "risk_level": "CRITICAL", "compliance_standard": "OSHA 1910.269 / CEA",
     "notes": "Arc flash protection mandatory in switchyard"},
    {"industry_type": "power_plant", "zone_type": "boiler",
     "required_ppe": ["no hardhat", "no gloves", "no boots", "no goggles"],
     "risk_level": "CRITICAL", "compliance_standard": "IBR 1950",
     "notes": "High pressure and temperature — full face protection"},

    # Shipbuilding
    {"industry_type": "shipbuilding", "zone_type": "general",
     "required_ppe": ["no hardhat", "no vest", "no boots", "no gloves"],
     "risk_level": "HIGH", "compliance_standard": "IRS / OSHA 1915",
     "notes": "Standard shipyard PPE"},
    {"industry_type": "shipbuilding", "zone_type": "blasting",
     "required_ppe": ["no hardhat", "no suit", "no gloves", "no goggles", "no mask"],
     "risk_level": "CRITICAL", "compliance_standard": "OSHA 1915.34",
     "notes": "Full body protection for abrasive blasting operations"},
    {"industry_type": "shipbuilding", "zone_type": "painting",
     "required_ppe": ["no mask", "no gloves", "no goggles", "no suit"],
     "risk_level": "HIGH", "compliance_standard": "OSHA 1915.35",
     "notes": "Respiratory and skin protection for painting operations"},

    # Mining
    {"industry_type": "mining", "zone_type": "general",
     "required_ppe": ["no hardhat", "no vest", "no boots"],
     "risk_level": "HIGH", "compliance_standard": "Mines Act 1952 / DGMS",
     "notes": "Mandatory PPE for all mining areas"},
    {"industry_type": "mining", "zone_type": "underground",
     "required_ppe": ["no hardhat", "no vest", "no boots", "no mask"],
     "risk_level": "CRITICAL", "compliance_standard": "DGMS Circular 4/2011",
     "notes": "Self-rescuer and cap lamp required underground"},
    {"industry_type": "mining", "zone_type": "blasting",
     "required_ppe": ["no hardhat", "no vest", "no boots", "no goggles", "no mask"],
     "risk_level": "CRITICAL", "compliance_standard": "Explosives Act 1884",
     "notes": "Full PPE for blast zone operations"},
]


# ── Request models ────────────────────────────────────────────

class PPEProfileCreate(BaseModel):
    industry_type: str = Field(min_length=2, max_length=50)
    zone_type: str = Field(min_length=2, max_length=50)
    required_ppe: List[str] = Field(min_length=1)
    risk_level: str = Field(default="HIGH", pattern="^(LOW|MEDIUM|HIGH|CRITICAL)$")
    compliance_standard: str = Field(default="OSHA 1910.132", max_length=100)
    notes: Optional[str] = Field(default=None, max_length=500)


# ── Routes ────────────────────────────────────────────────────

@router.post("/seed", status_code=201)
@limiter.limit(LIMIT_DEFAULT)
async def seed_profiles(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """
    Seed default industry PPE profiles (idempotent — skips existing).
    Call once on fresh deploy.
    """
    inserted = 0
    skipped = 0

    for profile in INDUSTRY_PPE_SEED:
        # Check if already exists
        result = await session.exec(text("""
            SELECT id FROM industry_ppe_profiles
            WHERE industry_type = :industry_type AND zone_type = :zone_type
        """).bindparams(
            industry_type=profile["industry_type"],
            zone_type=profile["zone_type"],
        ))
        if result.fetchone():
            skipped += 1
            continue

        await session.exec(text("""
            INSERT INTO industry_ppe_profiles
                (industry_type, zone_type, required_ppe, risk_level, compliance_standard, notes)
            VALUES
                (:industry_type, :zone_type, :required_ppe, :risk_level, :compliance_standard, :notes)
        """).bindparams(
            industry_type=profile["industry_type"],
            zone_type=profile["zone_type"],
            required_ppe=json.dumps(profile["required_ppe"]),
            risk_level=profile["risk_level"],
            compliance_standard=profile["compliance_standard"],
            notes=profile.get("notes"),
        ))
        inserted += 1

    logger.info("PPE profiles seeded | inserted={} | skipped={}", inserted, skipped)
    return {
        "inserted": inserted,
        "skipped": skipped,
        "total": len(INDUSTRY_PPE_SEED),
        "message": f"Seeded {inserted} profiles ({skipped} already existed)",
    }


@router.get("/profiles")
@limiter.limit(LIMIT_DEFAULT)
async def list_profiles(
    request: Request,
    industry_type: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    """List all industry PPE profiles, optionally filtered by industry."""
    where = ""
    params = {}
    if industry_type:
        where = "WHERE industry_type = :industry_type"
        params["industry_type"] = industry_type

    result = await session.exec(text(f"""
        SELECT id, industry_type, zone_type, required_ppe,
               risk_level, compliance_standard, notes
        FROM industry_ppe_profiles {where}
        ORDER BY industry_type, zone_type
    """).bindparams(**params) if params else text(f"""
        SELECT id, industry_type, zone_type, required_ppe,
               risk_level, compliance_standard, notes
        FROM industry_ppe_profiles {where}
        ORDER BY industry_type, zone_type
    """))

    rows = result.fetchall()
    profiles = []
    for row in rows:
        d = dict(row._mapping)
        try:
            d["required_ppe"] = json.loads(d["required_ppe"])
        except (json.JSONDecodeError, TypeError):
            d["required_ppe"] = []
        profiles.append(d)

    # Group by industry
    by_industry: dict = {}
    for p in profiles:
        ind = p["industry_type"]
        if ind not in by_industry:
            by_industry[ind] = []
        by_industry[ind].append(p)

    return {
        "total": len(profiles),
        "industries": list(by_industry.keys()),
        "profiles": profiles,
        "by_industry": by_industry,
    }


@router.get("/profiles/{industry_type}")
@limiter.limit(LIMIT_DEFAULT)
async def get_industry_profiles(
    request: Request,
    industry_type: str,
    session: AsyncSession = Depends(get_session),
):
    """Get all PPE profiles for a specific industry."""
    result = await session.exec(text("""
        SELECT id, industry_type, zone_type, required_ppe,
               risk_level, compliance_standard, notes
        FROM industry_ppe_profiles
        WHERE industry_type = :industry_type
        ORDER BY zone_type
    """).bindparams(industry_type=industry_type))

    rows = result.fetchall()
    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No PPE profiles found for industry '{industry_type}'. "
                   f"Try POST /industry-ppe/seed to load defaults."
        )

    profiles = []
    for row in rows:
        d = dict(row._mapping)
        try:
            d["required_ppe"] = json.loads(d["required_ppe"])
        except (json.JSONDecodeError, TypeError):
            d["required_ppe"] = []
        profiles.append(d)

    return {"industry_type": industry_type, "zones": len(profiles), "profiles": profiles}


@router.post("/profiles", status_code=201)
@limiter.limit(LIMIT_DEFAULT)
async def create_profile(
    request: Request,
    body: PPEProfileCreate,
    session: AsyncSession = Depends(get_session),
):
    """Add a custom PPE profile for an industry-zone combination."""
    # Check duplicate
    result = await session.exec(text("""
        SELECT id FROM industry_ppe_profiles
        WHERE industry_type = :industry_type AND zone_type = :zone_type
    """).bindparams(industry_type=body.industry_type, zone_type=body.zone_type))

    if result.fetchone():
        raise HTTPException(
            status_code=409,
            detail=f"Profile for {body.industry_type}/{body.zone_type} already exists. Use PATCH to update."
        )

    await session.exec(text("""
        INSERT INTO industry_ppe_profiles
            (industry_type, zone_type, required_ppe, risk_level, compliance_standard, notes)
        VALUES
            (:industry_type, :zone_type, :required_ppe, :risk_level, :compliance_standard, :notes)
    """).bindparams(
        industry_type=body.industry_type,
        zone_type=body.zone_type,
        required_ppe=json.dumps(body.required_ppe),
        risk_level=body.risk_level,
        compliance_standard=body.compliance_standard,
        notes=body.notes,
    ))

    return {
        "industry_type": body.industry_type,
        "zone_type": body.zone_type,
        "required_ppe": body.required_ppe,
        "risk_level": body.risk_level,
        "message": "PPE profile created",
    }


@router.get("/check")
@limiter.limit(LIMIT_DEFAULT)
async def check_compliance(
    request: Request,
    industry_type: str,
    zone_type: str,
    detected_class: str,
    session: AsyncSession = Depends(get_session),
):
    """
    Check if a detected class is a compliance violation for a given industry/zone.

    Example: /industry-ppe/check?industry_type=construction&zone_type=general&detected_class=no+hardhat
    Returns: is_violation, required_ppe, risk_level, compliance_standard
    """
    result = await session.exec(text("""
        SELECT required_ppe, risk_level, compliance_standard, notes
        FROM industry_ppe_profiles
        WHERE industry_type = :industry_type AND zone_type = :zone_type
    """).bindparams(industry_type=industry_type, zone_type=zone_type))

    row = result.fetchone()
    if not row:
        return {
            "is_violation": True,  # Default to violation if profile unknown
            "required_ppe": [],
            "risk_level": "MEDIUM",
            "compliance_standard": "OSHA 1910.132",
            "note": f"No profile found for {industry_type}/{zone_type} — treating as violation",
        }

    try:
        required = json.loads(row.required_ppe)
    except (json.JSONDecodeError, TypeError):
        required = []

    is_violation = detected_class.lower() in [r.lower() for r in required]

    return {
        "is_violation": is_violation,
        "detected_class": detected_class,
        "required_ppe": required,
        "risk_level": row.risk_level,
        "compliance_standard": row.compliance_standard,
        "notes": row.notes,
        "industry_type": industry_type,
        "zone_type": zone_type,
    }
