"""
backend/routes/__init__.py

Public API for FastAPI route registration.

# Usage:
    from backend.routes import (
        agent_router, alert_config_router, cameras_router,
        chat_router, detections_router, enhancement_router,
        fire_router, health_router, heatmap_router,
        mlops_router, pose_hazards_router, proximity_router,
        reports_router, shap_router, stream_router,
        weekly_report_router, workers_router, zones_router,
    )

# Example (in main.py):
    app.include_router(agent_router)
    app.include_router(stream_router)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import APIRouter

# ── Explicit public API ──────────────────────────────────────
__all__ = [
    "agent_router",
    "alert_config_router",
    "cameras_router",
    "chat_router",
    "detections_router",
    "enhancement_router",
    "fire_router",
    "health_router",
    "heatmap_router",
    "mlops_router",
    "pose_hazards_router",
    "proximity_router",
    "reports_router",
    "shap_router",
    "stream_router",
    "weekly_report_router",
    "workers_router",
    "zones_router",
]

__version__ = "1.0.0"
__author__ = "Chandrukumar S"
__description__ = "FastAPI route definitions for Industrial Safety Monitor"


# ── Lazy loader for route imports ────────────────────────────
def __getattr__(name: str):
    """Lazy-load route modules only when accessed."""
    
    if name == "agent_router":
        from . import agent_route as module
        return module.router
    
    if name == "alert_config_router":
        from . import alert_config_route as module
        return module.router
    
    if name == "cameras_router":
        from . import cameras_route as module
        return module.router
    
    if name == "chat_router":
        from . import chat as module
        return module.router
    
    if name == "detections_router":
        from . import detections as module
        return module.router
    
    if name == "enhancement_router":
        from . import enhancement_route as module
        return module.router
    
    if name == "fire_router":
        from . import fire_route as module
        return module.router
    
    if name == "health_router":
        from . import health as module
        return module.router
    
    if name == "heatmap_router":
        from . import heatmap as module
        return module.router
    
    if name == "mlops_router":
        from . import mlops_route as module
        return module.router
    
    if name == "pose_hazards_router":
        from . import pose_hazards as module
        return module.router
    
    if name == "proximity_router":
        from . import proximity_route as module
        return module.router
    
    if name == "reports_router":
        from . import reports_route as module
        return module.router
    
    if name == "shap_router":
        from . import shap_route as module
        return module.router
    
    if name == "stream_router":
        from . import stream as module
        return module.router
    
    if name == "weekly_report_router":
        from . import weekly_report_route as module
        return module.router
    
    if name == "workers_router":
        from . import workers_route as module
        return module.router
    
    if name == "zones_router":
        from . import zones_route as module
        return module.router
    
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")