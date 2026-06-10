"""
backend/alerts/__init__.py

Public API for the alert dispatch system.

# Usage:
    from backend.alerts import alert_worker, fire_alert_engine, zone_alert_engine
    from backend.alerts import AlertJob, ZoneAlert, PoseHazard  # Types
    from backend.alerts import send_whatsapp_alert, send_email_alert  # Direct send (testing)
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Type hints only — no runtime import cost
    from .alert_worker import AlertWorker, AlertJob
    from .email_sender import send_email_alert
    from .whatsapp_sender import send_whatsapp_alert
    from .fire_alert_engine import FireAlertEngine, FireDetection
    from .pose_alert_engine import PoseAlertEngine, PoseHazard, PoseLandmarks
    from .zone_alert_engine import ZoneAlertEngine, ZoneAlert, ZoneDefinition
    from .throttle import AlertThrottle

# ── Explicit public API ──────────────────────────────────────
__all__ = [
    # Core singletons (production use)
    "alert_worker",
    "fire_alert_engine",
    "pose_alert_engine", 
    "zone_alert_engine",
    "alert_throttle",
    
    # Types (for type hints)
    "AlertJob",
    "ZoneAlert", 
    "PoseHazard",
    "ZoneDefinition",
    "FireDetection",
    "PoseLandmarks",
    
    # Direct send functions (testing/CLI use only)
    "send_email_alert",
    "send_whatsapp_alert",
    
    # Config validation (call at app startup)
    "validate_alert_config",
]

__version__ = "1.1.0"
__author__ = "Chandrukumar S"
__description__ = "Real-time alert dispatch system for industrial safety monitoring"


# ── Config validation at import time ─────────────────────────
def validate_alert_config() -> list[str]:
    """
    Validate critical alert config at startup.
    Returns list of errors (empty = OK).
    """
    errors = []
    
    # SMTP
    if os.getenv("ENABLE_EMAIL_ALERTS", "true").lower() == "true":
        if not all([os.getenv("SMTP_USERNAME"), os.getenv("SMTP_PASSWORD"), os.getenv("SMTP_FROM_EMAIL")]):
            errors.append("Email alerts enabled but SMTP credentials incomplete")
    
    # Twilio
    if os.getenv("ENABLE_WHATSAPP_ALERTS", "true").lower() == "true":
        if not all([os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN")]):
            errors.append("WhatsApp alerts enabled but Twilio credentials incomplete")
    
    # Throttle config
    try:
        throttle_min = int(os.getenv("ALERT_THROTTLE_MINUTES", "5"))
        if throttle_min < 1:
            errors.append(f"ALERT_THROTTLE_MINUTES must be >= 1, got {throttle_min}")
    except ValueError:
        errors.append("ALERT_THROTTLE_MINUTES must be an integer")
    
    return errors


# ── Lazy loader for heavy imports ────────────────────────────
def __getattr__(name: str) -> Any:
    """Lazy-load submodules only when accessed."""
    
    if name in ("alert_worker", "AlertJob"):
        from . import alert_worker
        return getattr(alert_worker, name)
    
    if name in ("send_email_alert",):
        from . import email_sender
        return getattr(email_sender, name)
    
    if name in ("send_whatsapp_alert",):
        from . import whatsapp_sender
        return getattr(whatsapp_sender, name)
    
    if name in ("fire_alert_engine", "FireDetection"):
        from . import fire_alert_engine
        return getattr(fire_alert_engine, name)
    
    if name in ("pose_alert_engine", "PoseHazard", "PoseLandmarks"):
        from . import pose_alert_engine
        return getattr(pose_alert_engine, name)
    
    if name in ("zone_alert_engine", "ZoneAlert", "ZoneDefinition"):
        from . import zone_alert_engine
        return getattr(zone_alert_engine, name)
    
    if name in ("alert_throttle",):
        from . import throttle
        return getattr(throttle, name)
    
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


# ── Run validation once at import ────────────────────────────
_config_errors = validate_alert_config()
if _config_errors:
    import warnings
    warnings.warn(
        "Alert config warnings:\n  • " + "\n  • ".join(_config_errors),
        RuntimeWarning,
        stacklevel=2,
    )