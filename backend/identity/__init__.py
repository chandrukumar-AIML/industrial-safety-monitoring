"""
backend/identity/__init__.py

Public API for worker identity & privacy utilities.

# Usage:
    from backend.identity import (
        face_blurrer, face_recognizer, compute_worker_risk,
        WorkerProfile, RiskLevel, PrivacyMode,
    )
    from backend.identity import IdentityError, PrivacyViolationError  # Exceptions

# Example:
    blurred = face_blurrer.blur(frame_bgr)
    matches = await face_recognizer.identify(frame_bgr)
    risk = await compute_worker_risk("worker-123", db_factory)
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .face_blurrer import FaceBlurrer
    from .face_recognizer import FaceRecognizer, WorkerMatch
    from .risk_scorer import RiskLevel, compute_worker_risk, update_all_risk_scores
    from .worker_registry import WorkerProfile, WorkerRegistry

# ── Explicit public API ──────────────────────────────────────
__all__ = [
    # Core classes
    "FaceBlurrer",
    "FaceRecognizer",
    "WorkerProfile",
    "WorkerRegistry",
    
    # Data classes
    "WorkerMatch",
    "RiskLevel",
    "PrivacyMode",
    
    # Functions
    "compute_worker_risk",
    "update_all_risk_scores",
    "enroll_worker",
    "identify_worker",
    
    # Singletons
    "face_blurrer",
    "face_recognizer",
    "worker_registry",
    
    # Exceptions
    "IdentityError",
    "PrivacyViolationError",
    "EnrollmentError",
    "RecognitionError",
    
    # Config helpers
    "get_identity_config",
    "validate_identity_config",
]

__version__ = "1.0.0"
__author__ = "Chandrukumar S"
__description__ = "Worker identity, face privacy & risk scoring for Industrial Safety Monitor"


# ── Config helpers ───────────────────────────────────────────
def get_identity_config() -> dict:
    """Return current identity system configuration."""
    from .face_blurrer import _DEFAULT_BLUR_KERNEL, _DEFAULT_FACE_CONFIDENCE
    from .face_recognizer import FACE_MODEL, DIST_THRESHOLD, RECOGNITION_ON
    from .risk_scorer import HIGH_THRESHOLD, CRITICAL_THRESHOLD, HR_COOLDOWN_HOURS
    
    return {
        "privacy": {
            "blur_kernel": _DEFAULT_BLUR_KERNEL,
            "face_detection_confidence": _DEFAULT_FACE_CONFIDENCE,
            "gdpr_mode": os.getenv("GDPR_MODE", "strict").lower(),
        },
        "recognition": {
            "enabled": RECOGNITION_ON,
            "model": FACE_MODEL,
            "distance_threshold": DIST_THRESHOLD,
        },
        "risk_scoring": {
            "high_threshold": HIGH_THRESHOLD,
            "critical_threshold": CRITICAL_THRESHOLD,
            "hr_alert_cooldown_hours": HR_COOLDOWN_HOURS,
            "history_days": int(os.getenv("RISK_HISTORY_DAYS", "7")),
        },
    }


def validate_identity_config() -> list[str]:
    """
    Validate identity config at startup.
    Returns list of warnings (empty = OK).
    """
    warnings = []
    
    # GDPR mode validation
    gdpr_mode = os.getenv("GDPR_MODE", "strict").lower()
    if gdpr_mode not in ("strict", "relaxed", "disabled"):
        warnings.append(f"Invalid GDPR_MODE: {gdpr_mode} — using 'strict'")
    
    # Face recognition dependencies
    if os.getenv("FACE_RECOGNITION_ENABLED", "true").lower() == "true":
        try:
            import deepface  # noqa: F401
        except ImportError:
            warnings.append("DeepFace not installed — face recognition will be disabled")
    
    # Threshold validation
    try:
        dist_thresh = float(os.getenv("FACE_DISTANCE_THRESHOLD", "0.50"))
        if not 0 <= dist_thresh <= 1:
            warnings.append(f"FACE_DISTANCE_THRESHOLD={dist_thresh} outside 0-1 range")
    except ValueError:
        warnings.append("FACE_DISTANCE_THRESHOLD must be a float")
    
    # Risk thresholds
    try:
        high = float(os.getenv("RISK_SCORE_HIGH_THRESHOLD", "15.0"))
        critical = float(os.getenv("RISK_SCORE_CRITICAL_THRESHOLD", "25.0"))
        if critical <= high:
            warnings.append(f"CRITICAL_THRESHOLD ({critical}) must be > HIGH_THRESHOLD ({high})")
    except ValueError:
        warnings.append("Risk thresholds must be numeric")
    
    return warnings


# ── Lazy loader for heavy imports ────────────────────────────
def __getattr__(name: str) -> Any:
    """Lazy-load submodules only when accessed."""
    
    if name in ("FaceBlurrer", "face_blurrer"):
        from . import face_blurrer as module
        return getattr(module, name)
    
    if name in ("FaceRecognizer", "WorkerMatch", "face_recognizer"):
        from . import face_recognizer as module
        return getattr(module, name)
    
    if name in ("WorkerProfile", "WorkerRegistry", "worker_registry"):
        from . import worker_registry as module
        return getattr(module, name)
    
    if name in ("RiskLevel", "compute_worker_risk", "update_all_risk_scores"):
        from . import risk_scorer as module
        return getattr(module, name)
    
    if name in ("PrivacyMode",):
        from . import worker_registry as module
        return getattr(module, name)
    
    if name in ("IdentityError", "PrivacyViolationError", "EnrollmentError", "RecognitionError"):
        from . import worker_registry as module
        return getattr(module, name)
    
    if name in ("enroll_worker", "identify_worker"):
        from . import face_recognizer as module
        return getattr(module, name)
    
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


# ── Run validation at import (non-blocking warnings) ─────────
_identity_warnings = validate_identity_config()
if _identity_warnings and os.getenv("IDENTITY_STRICT_MODE", "false").lower() == "true":
    import warnings as _warnings
    for w in _identity_warnings:
        _warnings.warn(f"Identity config: {w}", RuntimeWarning, stacklevel=2)


# ── Convenience wrappers ─────────────────────────────────────
async def enroll_worker(
    image_bgr,
    worker_id: str,
    worker_name: str,
    db_factory,
) -> bool:
    """Convenience: enroll worker face + save to DB."""
    from .face_recognizer import face_recognizer
    from .worker_registry import upsert_worker_profile
    
    embedding_bytes = face_recognizer.enroll_from_image(image_bgr, worker_id, worker_name)
    if embedding_bytes:
        await upsert_worker_profile(
            worker_id=worker_id,
            full_name=worker_name,
            face_embedding=embedding_bytes,
            db_factory=db_factory,
        )
        return True
    return False


async def identify_worker(
    frame_bgr,
    db_factory=None,
    **kwargs,
) -> list:
    """Convenience: identify workers + enrich with profile data."""
    from .face_recognizer import face_recognizer
    
    matches = face_recognizer.identify(frame_bgr, **kwargs)
    
    # Optional: enrich with profile data from DB
    if db_factory and matches:
        from .worker_registry import get_worker_profile
        enriched = []
        for match in matches:
            profile = await get_worker_profile(match.worker_id, db_factory)
            if profile:
                enriched.append({
                    **match.__dict__,
                    "department": profile.department,
                    "role": profile.role,
                    "risk_level": profile.risk_level,
                })
            else:
                enriched.append(match.__dict__)
        return enriched
    
    return [m.__dict__ for m in matches]