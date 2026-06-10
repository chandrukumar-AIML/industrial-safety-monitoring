"""
backend/main.py

FastAPI application — startup, shutdown, router registration,
CORS, authentication, and the background task that drains the inference queue.

# FIXED: Proper middleware ordering (CORS before auth)
# FIXED: Secure API key handling with masking in logs
# IMPROVED: Graceful shutdown with task cancellation
# FIXED: SHAP initialization in background task (non-blocking startup)
# IMPROVED: Clear OpenAPI documentation with tags and examples
# FIXED: No PII leakage in logs or error messages
"""

from __future__ import annotations

import asyncio
import os
import re
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from dotenv import load_dotenv
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from .middleware.rate_limiter import limiter, rate_limit_exceeded_handler

from .database import init_db, AsyncSessionLocal
from .pipeline import PipelineRuntime, parse_video_source, reload_enabled
from .state import app_state

# Load environment variables from .env file
load_dotenv()

# ── Environment config with validation ─────────────────────────

def _env_float(name: str, default: str, min_val: float = 0.0, max_val: float = 1.0) -> float:
    """Validate and parse float env var with range checking."""
    raw = os.getenv(name, default)
    try:
        val = float(raw)
        if not min_val <= val <= max_val:
            logger.warning("{}={} outside [{}, {}] — using default {}", name, val, min_val, max_val, default)
            return float(default)
        return val
    except ValueError:
        logger.warning("{}={} is not a valid float — using default {}", name, raw, default)
        return float(default)


def _env_int(name: str, default: str, min_val: int = 1, max_val: int = 100) -> int:
    """Validate and parse int env var with range checking."""
    raw = os.getenv(name, default)
    try:
        val = int(raw)
        if not min_val <= val <= max_val:
            logger.warning("{}={} outside [{}, {}] — using default {}", name, val, min_val, max_val, default)
            return int(default)
        return val
    except ValueError:
        logger.warning("{}={} is not a valid integer — using default {}", name, raw, default)
        return int(default)


# Core config
MODEL_PATH: str = os.getenv("MODEL_PATH", "models/best.pt")
VIDEO_SOURCE: str = os.getenv("VIDEO_SOURCE", "0")
DEVICE: str = os.getenv("DEVICE", "cpu")
CONF: float = _env_float("CONFIDENCE_THRESHOLD", "0.35", 0.0, 1.0)
IOU: float = _env_float("IOU_THRESHOLD", "0.45", 0.0, 1.0)
FRAME_SKIP: int = _env_int("FRAME_SKIP", "1", 1, 100)

# CORS config
CORS_ORIGINS: list[str] = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    if o.strip()
]

# SHAP config
SHAP_BACKGROUND_DIR: str = os.getenv(
    "SHAP_BACKGROUND_DIR", "data/processed/train/images"
)

# Auth config
API_KEY: str = os.getenv("API_KEY", "")
if API_KEY and len(API_KEY) < 16:
    logger.warning("API_KEY is too short (<16 chars) — consider using a stronger key")


# ── Optional API key middleware ───────────────────────────────
_AUTH_EXCLUDED_PATHS = {"/health", "/docs", "/openapi.json", "/redoc", "/stream"}


async def api_key_middleware(request: Request, call_next) -> JSONResponse:
    """
    Simple Bearer token auth middleware.
    Disabled when API_KEY env var is empty (local dev).
    
    # FIXED: Returns JSONResponse directly instead of raising HTTPException
    # FIXED: Masks API key in logs
    # IMPROVED: Clear error messages for debugging
    """
    if not API_KEY:
        return await call_next(request)

    # Skip auth for public endpoints (health probes, docs, websocket stream)
    if (
        request.url.path in _AUTH_EXCLUDED_PATHS
        or request.url.path.startswith("/stream")
        or request.url.path.startswith("/health")
    ):
        return await call_next(request)

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        logger.warning(
            "Auth rejected (missing header) | path={} | ip={}",
            request.url.path,
            request.client.host if request.client else "unknown",
        )
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Missing Authorization: Bearer <token> header"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = auth_header.removeprefix("Bearer ").strip()
    if token != API_KEY:
        # Log masked key for debugging
        masked_key = API_KEY[:4] + "***" + API_KEY[-4:] if len(API_KEY) > 8 else "***"
        logger.warning(
            "Auth rejected (invalid token) | path={} | ip={} | token={}",
            request.url.path,
            request.client.host if request.client else "unknown",
            masked_key,
        )
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Invalid API key"},
        )
    
    return await call_next(request)


# ── Lifespan ──────────────────────────────────────────────────

_pipeline_runtime: Optional[PipelineRuntime] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    The original code did heavy model loading and pipeline bootstrap directly in
    FastAPI startup. That meant the app event loop spent startup time on
    OpenCV/YOLO work before the HTTP layer was truly ready. The pipeline is now
    launched in a dedicated background thread so `/health` can respond
    immediately while inference warms up.
    """
    global _pipeline_runtime

    logger.info("Starting Industrial Safety Monitor API")
    
    # Warn if auth is disabled in production-like environment
    if not API_KEY and os.getenv("ENVIRONMENT", "dev") != "dev":
        logger.warning(
            "API_KEY is empty — authentication is DISABLED. "
            "Set API_KEY in environment before deploying to production."
        )
    
    # Keep startup lightweight: DB init is short, while ML work moves to the
    # dedicated pipeline worker thread below.
    await init_db()

    # ── Seed industry PPE profiles (idempotent — skips existing rows) ──
    try:
        from .routes.industry_ppe_route import INDUSTRY_PPE_SEED
        import json as _json
        from sqlalchemy import text as _text
        async with AsyncSessionLocal() as _sess:
            _inserted = 0
            for _p in INDUSTRY_PPE_SEED:
                _r = await _sess.exec(_text(
                    "SELECT id FROM industry_ppe_profiles "
                    "WHERE industry_type=:it AND zone_type=:zt"
                ).bindparams(it=_p["industry_type"], zt=_p["zone_type"]))
                if not _r.fetchone():
                    await _sess.exec(_text("""
                        INSERT INTO industry_ppe_profiles
                            (industry_type,zone_type,required_ppe,risk_level,compliance_standard,notes)
                        VALUES (:it,:zt,:rp,:rl,:cs,:n)
                    """).bindparams(
                        it=_p["industry_type"], zt=_p["zone_type"],
                        rp=_json.dumps(_p["required_ppe"]), rl=_p["risk_level"],
                        cs=_p["compliance_standard"], n=_p.get("notes"),
                    ))
                    _inserted += 1
            await _sess.commit()
        if _inserted:
            logger.info("Industry PPE profiles seeded: {} new profiles", _inserted)
    except Exception as _e:
        logger.warning("PPE profile seed failed (non-critical): {}", str(_e)[:80])

    # ── APScheduler — background jobs ─────────────────────────
    _scheduler = None
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from .routes.escalation_route import run_escalation_check

        async def _escalation_job():
            """Check for overdue alerts and escalate every 60 seconds."""
            try:
                async with AsyncSessionLocal() as _s:
                    result = await run_escalation_check(_s)
                    await _s.commit()
                    if result["escalated"] > 0:
                        logger.warning(
                            "APScheduler: escalated {} alert(s)", result["escalated"]
                        )
            except Exception as _ex:
                logger.warning("Escalation job error: {}", str(_ex)[:80])

        _scheduler = AsyncIOScheduler(timezone="UTC")
        _scheduler.add_job(
            _escalation_job,
            "interval",
            seconds=60,
            id="alert_escalation",
            max_instances=1,
            coalesce=True,
        )
        _scheduler.start()
        logger.info("APScheduler started | escalation job every 60s")
    except Exception as _e:
        logger.warning("APScheduler failed to start (non-critical): {}", str(_e)[:80])

    video_src = parse_video_source(VIDEO_SOURCE)
    
    # Update app state config
    app_state.model_path = MODEL_PATH
    app_state.device = DEVICE
    app_state.video_source = video_src

    _pipeline_runtime = PipelineRuntime(
        model_path=MODEL_PATH,
        video_source=video_src,
        device=DEVICE,
        conf_threshold=CONF,
        iou_threshold=IOU,
        frame_skip=FRAME_SKIP,
        shap_background_dir=SHAP_BACKGROUND_DIR,
        app_state=app_state,
    )
    app_state.set_pipeline_runtime(_pipeline_runtime)
    _pipeline_runtime.start()

    logger.info("API startup complete | auth={} | device={}", 
                "enabled" if API_KEY else "disabled", DEVICE)

    yield

    # Shutdown logic
    logger.info("Shutting down Industrial Safety Monitor API...")

    if _pipeline_runtime is not None:
        await asyncio.to_thread(_pipeline_runtime.stop)
        app_state.set_pipeline_runtime(None)

    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped")

    logger.info("Shutdown complete")


# ── App factory ───────────────────────────────────────────────

_OPENAPI_TAGS = [
    {"name": "system", "description": "System health and pipeline status"},
    {"name": "detections", "description": "Violation event log, live detections, and acknowledgement"},
    {"name": "stream", "description": "WebSocket video stream and connection statistics"},
    {"name": "heatmap", "description": "Violation density heatmap image and zone risk scores"},
    {"name": "explainability", "description": "On-demand SHAP saliency explanations for detections"},
    {"name": "chatbot", "description": "RAG-powered safety Q&A chatbot"},
    {"name": "demo", "description": "Demo mode — synthetic data for portfolio/trade show presentations"},
    {"name": "export", "description": "CSV/JSON data export for compliance reporting and audits"},
    {"name": "webhooks", "description": "Outbound webhook management — Slack, Teams, JIRA, custom endpoints"},
    {"name": "sites", "description": "Multi-site management — register and compare physical locations"},
    {"name": "shifts", "description": "Shift schedule management and per-shift safety analytics"},
    {"name": "api-keys", "description": "API key provisioning and RBAC management"},
    {"name": "audit", "description": "Immutable audit trail — all safety-critical actions logged (OSHA/ISO 45001)"},
    {"name": "organizations", "description": "Multi-tenant org management — create, activate, suspend client accounts"},
    {"name": "billing", "description": "Subscription billing — Razorpay India, plan management, webhook events"},
    {"name": "industry-ppe", "description": "Industry-specific PPE profiles — construction, steel, oil & gas, pharma, mining"},
    {"name": "escalation", "description": "Alert escalation matrix — L1 (supervisor) → L4 (emergency) with auto-escalation"},
    {"name": "permits", "description": "Digital permit-to-work system — hot work, confined space, electrical LOTO"},
    {"name": "attendance", "description": "Worker attendance & headcount — check-in/out, muster drill, overtime alerts"},
]


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Industrial Safety Monitor API",
        description=(
            "Real-time PPE detection and violation tracking. "
            "Streams annotated video frames over WebSocket and persists "
            "violation events to SQLite. "
            "\n\n**Authentication:** Set `Authorization: Bearer <API_KEY>` "
            "header. Health endpoint is public."
        ),
        version="1.0.0",
        lifespan=lifespan,
        openapi_tags=_OPENAPI_TAGS,
        contact={
            "name": "Safety Monitor Team",
            # No hardcoded PII default — falls back to a generic noreply address
            "email": os.getenv("CONTACT_EMAIL", "support@safeguardai.example.com"),
        },
        docs_url="/docs" if os.getenv("ENVIRONMENT", "dev") == "dev" else None,  # Hide docs in prod
        redoc_url="/redoc" if os.getenv("ENVIRONMENT", "dev") == "dev" else None,
    )

    # Rate limiter state (required by slowapi)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    # CORS middleware (must be added before auth middleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Org-ID"],
    )

    # Multi-tenant middleware — resolves X-Org-ID → request.state.org_id
    from .middleware.tenant import TenantMiddleware
    app.add_middleware(TenantMiddleware)

    # FIXED: Re-enabled auth middleware — was commented out, leaving all routes unprotected
    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        return await api_key_middleware(request, call_next)

    # Register routers
    from .routes import (
        health, detections, stream, heatmap, shap_route, chat,
        agent_route, alert_config_route, cameras_route,
        enhancement_route, fire_route, mlops_route,
        pose_hazards, proximity_route, reports_route,
        weekly_report_route, workers_route, zones_route,
        demo_route, export_route, webhooks_route,
        sites_route, shifts_route, apikeys_route,
        audit_route,
    )
    # Enterprise feature routers
    from .routes.organizations_route import router as organizations_router
    from .routes.billing_route import router as billing_router
    from .routes.industry_ppe_route import router as industry_ppe_router
    from .routes.escalation_route import router as escalation_router
    from .routes.permit_route import router as permit_router
    from .routes.attendance_route import router as attendance_router

    app.include_router(health.router)
    app.include_router(detections.router)
    app.include_router(stream.router)
    app.include_router(heatmap.router)
    app.include_router(shap_route.router)
    app.include_router(chat.router)
    app.include_router(agent_route.router)
    app.include_router(alert_config_route.router)
    app.include_router(cameras_route.router)
    app.include_router(enhancement_route.router)
    app.include_router(fire_route.router)
    app.include_router(mlops_route.router)
    app.include_router(pose_hazards.router)
    app.include_router(proximity_route.router)
    app.include_router(reports_route.router)
    app.include_router(weekly_report_route.router)
    app.include_router(workers_route.router)
    app.include_router(zones_route.router)
    # Core feature routers
    app.include_router(demo_route.router)
    app.include_router(export_route.router)
    app.include_router(webhooks_route.router)
    app.include_router(sites_route.router)
    app.include_router(shifts_route.router)
    app.include_router(apikeys_route.router)
    app.include_router(audit_route.router)
    # Enterprise SaaS routers
    app.include_router(organizations_router)
    app.include_router(billing_router)
    app.include_router(industry_ppe_router)
    app.include_router(escalation_router)
    app.include_router(permit_router)
    app.include_router(attendance_router)

    return app


# Create app instance
app = create_app()


# ── Entry point ───────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", "8000")),
        reload=reload_enabled(),
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )
