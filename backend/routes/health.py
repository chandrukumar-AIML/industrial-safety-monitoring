"""
backend/routes/health.py

System health check endpoint.

# FIXED: Proper status code handling (200 vs 503)
# IMPROVED: Clear health status semantics
# FIXED: No PII leakage in logs
# IMPROVED: Dependency injection for testability
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from loguru import logger

from ..state import app_state
from ..models import SystemStatus

router = APIRouter(prefix="/health", tags=["system"])


@router.get(
    "",
    response_model=SystemStatus,
    responses={
        200: {
            "description": "System healthy and pipeline running",
            "model": SystemStatus,
        },
        503: {
            "description": "API is up but inference pipeline is not running",
            "content": {
                "application/json": {
                    "example": {
                        "status": "degraded",
                        "pipeline_running": False,
                        "active_tracks": 0,
                        "fps": 0.0,
                        "uptime_s": 12.3,
                        "model_path": "models/best.pt",
                        "device": "cpu",
                        "video_source": "0",
                    }
                }
            },
        },
    },
    summary="System health check",
    description=(
        "Returns pipeline status, active track count, and FPS. "
        "Returns HTTP 200 when the inference pipeline is running, "
        "HTTP 503 when the pipeline is stopped or crashed. "
        "Used by Railway healthcheck and the React dashboard header."
    ),
)
async def health_check() -> JSONResponse:
    """
    Health check endpoint.

    Returns 200 when pipeline is running, 503 when pipeline is stopped.
    Railway's healthcheck uses this to decide whether to restart the container.
    """
    latest = app_state.get_latest_frame()
    pipeline_running = app_state.pipeline_running

    body = SystemStatus(
        status="ok" if pipeline_running else "degraded",
        pipeline_running=pipeline_running,
        active_tracks=latest.active_tracks if latest else 0,
        fps=latest.fps if latest else 0.0,
        uptime_s=app_state.uptime_seconds,
        model_path=app_state.model_path,
        device=app_state.device,
        video_source=str(app_state.video_source),
    )

    # Return 503 when pipeline is down so Railway healthcheck
    # and uptime monitors correctly detect a degraded service.
    status_code = 200 if pipeline_running else 503
    return JSONResponse(
        content=body.model_dump(mode="json"),
        status_code=status_code,
    )


@router.get(
    "/live",
    summary="Liveness probe",
    description="Always returns 200 if the process is running. Used by k8s/Railway liveness checks.",
)
async def liveness() -> JSONResponse:
    """Liveness probe — process is up. No dependency checks."""
    return JSONResponse(content={"status": "alive"}, status_code=200)


@router.get(
    "/ready",
    summary="Readiness probe (checks DB)",
    description=(
        "Verifies the service can actually serve traffic by pinging real "
        "dependencies (database). Returns 503 if any dependency is unreachable. "
        "Used by load balancers to decide whether to route traffic."
    ),
)
async def readiness() -> JSONResponse:
    """
    Readiness probe — checks real dependency health (DB connection).

    Unlike `/health` (which reports pipeline status), this verifies the
    database is reachable so a load balancer knows whether to send traffic.
    Returns 200 only when all critical dependencies respond.
    """
    from sqlalchemy import text as _text
    from ..database import AsyncSessionLocal

    checks: dict[str, str] = {}
    all_ok = True

    # ── Database connectivity ──
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(_text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 — readiness must report, not crash
        checks["database"] = "unreachable"
        all_ok = False
        logger.warning("Readiness: DB check failed: {}", str(exc)[:120])

    return JSONResponse(
        content={"status": "ready" if all_ok else "not_ready", "checks": checks},
        status_code=200 if all_ok else 503,
    )


def get_diagnostics() -> dict:
    """Return health router status for health checks."""
    status, error = app_state.get_pipeline_status()
    return {
        "pipeline_running": app_state.pipeline_running,
        "pipeline_status": status,
        "pipeline_error": error,
        "latest_frame_available": app_state.get_latest_frame() is not None,
        "uptime_seconds": app_state.uptime_seconds,
    }
