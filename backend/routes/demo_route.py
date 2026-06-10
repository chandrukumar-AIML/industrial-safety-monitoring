"""
backend/routes/demo_route.py

Demo Mode API — portfolio showcase endpoints.
Returns synthetic realistic data when DEMO_MODE=true.

All endpoints mirror their real counterparts but return
generated data instead of querying the live DB/camera.

Used for:
  - Portfolio presentations (no camera hardware needed)
  - Client demos at trade shows
  - CI/CD integration testing
  - Onboarding new team members

Enable: DEMO_MODE=true in .env
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from loguru import logger

from ..demo.synthetic_data import (
    is_demo_mode,
    generate_violation_event,
    generate_worker_profiles,
    generate_zone_definitions,
    generate_camera_list,
    generate_dashboard_stats,
    generate_violation_history,
    generate_compliance_by_class,
    generate_weekly_report_summary,
    generate_fire_alert,
    generate_pose_hazards,
)

router = APIRouter(prefix="/demo", tags=["demo"])

_DEMO_DISABLED_MSG = (
    "Demo mode is disabled. Set DEMO_MODE=true in your .env file to enable "
    "synthetic data for portfolio/demo presentations."
)


def _require_demo():
    if not is_demo_mode():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_DEMO_DISABLED_MSG,
        )


@router.get("/status")
async def demo_status() -> dict:
    """Check if demo mode is active."""
    return {
        "demo_mode": is_demo_mode(),
        "message": (
            "Demo mode is ACTIVE — all data is synthetic."
            if is_demo_mode()
            else "Demo mode is disabled. Set DEMO_MODE=true to enable."
        ),
    }


@router.get("/violations")
async def demo_violations(count: int = 20) -> list:
    """Get synthetic violation events (demo mode)."""
    _require_demo()
    count = max(1, min(count, 100))
    return [generate_violation_event(i * 30) for i in range(count)]


@router.get("/workers")
async def demo_workers() -> list:
    """Get synthetic worker profiles (demo mode)."""
    _require_demo()
    return generate_worker_profiles()


@router.get("/zones")
async def demo_zones() -> list:
    """Get synthetic zone definitions (demo mode)."""
    _require_demo()
    return generate_zone_definitions()


@router.get("/cameras")
async def demo_cameras() -> list:
    """Get synthetic camera list (demo mode)."""
    _require_demo()
    return generate_camera_list()


@router.get("/dashboard")
async def demo_dashboard() -> dict:
    """Get synthetic dashboard KPIs (demo mode)."""
    _require_demo()
    return generate_dashboard_stats()


@router.get("/history")
async def demo_history(days: int = 30) -> list:
    """Get synthetic violation history for charts (demo mode)."""
    _require_demo()
    days = max(7, min(days, 90))
    return generate_violation_history(days)


@router.get("/compliance-by-class")
async def demo_compliance_by_class() -> dict:
    """Get synthetic violation counts by PPE class (demo mode)."""
    _require_demo()
    return generate_compliance_by_class()


@router.get("/weekly-report")
async def demo_weekly_report() -> dict:
    """Get synthetic weekly report summary (demo mode)."""
    _require_demo()
    return generate_weekly_report_summary()


@router.get("/fire-alert")
async def demo_fire_alert() -> dict:
    """Get a synthetic fire detection event (demo mode)."""
    _require_demo()
    return generate_fire_alert()


@router.get("/pose-hazards")
async def demo_pose_hazards() -> list:
    """Get synthetic pose hazard events (demo mode)."""
    _require_demo()
    return generate_pose_hazards()


@router.get("/full-dataset")
async def demo_full_dataset() -> dict:
    """
    Get the complete synthetic dataset in one call.
    Use this for portfolio pages that need to populate all panels at once.
    """
    _require_demo()
    logger.info("Demo full-dataset requested")
    return {
        "dashboard": generate_dashboard_stats(),
        "violations": [generate_violation_event(i * 30) for i in range(15)],
        "workers": generate_worker_profiles(),
        "zones": generate_zone_definitions(),
        "cameras": generate_camera_list(),
        "history": generate_violation_history(30),
        "compliance_by_class": generate_compliance_by_class(),
        "weekly_report": generate_weekly_report_summary(),
        "pose_hazards": generate_pose_hazards(),
        "demo_mode": True,
    }
