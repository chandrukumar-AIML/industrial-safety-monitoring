"""
backend/monitoring/__init__.py

Public API for monitoring and drift detection utilities.

# Usage:
    from backend.monitoring import (
        detect_drift, DriftResult,
        stats_accumulator, flush_stats_to_db,
        load_reference, save_reference,
        run_daily_drift_check,
    )
    from backend.monitoring import MonitoringError, DriftDetectionError  # Exceptions

# Example:
    result = detect_drift(reference_stats, production_stats)
    if result.drift_detected:
        await run_daily_drift_check(db_factory)
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .drift_detector import DriftResult, detect_drift
    from .inference_logger import DailyStatsAccumulator, stats_accumulator, flush_stats_to_db
    from .reference_store import load_reference, save_reference
    from .drift_reporter import run_daily_drift_check

# ── Explicit public API ──────────────────────────────────────
__all__ = [
    # Core functions
    "detect_drift",
    "run_daily_drift_check",
    "load_reference",
    "save_reference",
    "flush_stats_to_db",
    
    # Classes
    "DriftResult",
    "DailyStatsAccumulator",
    
    # Singletons
    "stats_accumulator",
    
    # Exceptions
    "MonitoringError",
    "DriftDetectionError",
    "ReferenceStoreError",
    
    # Config helpers
    "get_monitoring_config",
    "validate_monitoring_config",
]

__version__ = "1.0.0"
__author__ = "Chandrukumar S"
__description__ = "Monitoring utilities for model drift detection and inference statistics"


# ── Config helpers ───────────────────────────────────────────
def get_monitoring_config() -> dict:
    """Return current monitoring configuration."""
    from .drift_detector import PSI_THRESHOLD, KS_PVALUE_THRESH
    from .reference_store import REFERENCE_PATH
    
    return {
        "drift_detection": {
            "psi_threshold": PSI_THRESHOLD,
            "ks_pvalue_threshold": KS_PVALUE_THRESH,
        },
        "reference_store": {
            "path": str(REFERENCE_PATH),
        },
        "reporting": {
            "enabled": os.getenv("MONITORING_REPORTS_ENABLED", "true").lower() == "true",
            "report_dir": os.getenv("MONITORING_REPORT_DIR", "./monitoring/drift_reports"),
        },
    }


def validate_monitoring_config() -> list[str]:
    """
    Validate monitoring config at startup.
    Returns list of warnings (empty = OK).
    """
    warnings = []
    
    # Reference path
    ref_path = os.getenv("REFERENCE_STATS_PATH", "./monitoring/reference_stats.json")
    if not os.path.isabs(ref_path):
        ref_path = os.path.abspath(ref_path)
    allowed_dirs = [os.path.abspath(d.strip()) for d in os.getenv("ALLOWED_MONITORING_DIRS", "./monitoring").split(",") if d.strip()]
    if not any(ref_path.startswith(d) for d in allowed_dirs):
        warnings.append(f"REFERENCE_STATS_PATH not in allowed directories: {ref_path}")
    
    # Thresholds
    try:
        psi_thresh = float(os.getenv("DRIFT_PSI_THRESHOLD", "0.2"))
        if not 0 <= psi_thresh <= 1:
            warnings.append(f"DRIFT_PSI_THRESHOLD={psi_thresh} outside 0-1 range")
    except ValueError:
        warnings.append("DRIFT_PSI_THRESHOLD must be a float")
    
    try:
        ks_pval = float(os.getenv("DRIFT_KS_PVALUE_THRESHOLD", "0.05"))
        if not 0 < ks_pval < 1:
            warnings.append(f"DRIFT_KS_PVALUE_THRESHOLD={ks_pval} outside 0-1 range")
    except ValueError:
        warnings.append("DRIFT_KS_PVALUE_THRESHOLD must be a float")
    
    return warnings


# ── Lazy loader for heavy imports ────────────────────────────
def __getattr__(name: str) -> Any:
    """Lazy-load submodules only when accessed."""
    
    if name in ("DriftResult", "detect_drift"):
        from . import drift_detector as module
        return getattr(module, name)
    
    if name in ("DailyStatsAccumulator", "stats_accumulator", "flush_stats_to_db"):
        from . import inference_logger as module
        return getattr(module, name)
    
    if name in ("load_reference", "save_reference"):
        from . import reference_store as module
        return getattr(module, name)
    
    if name in ("run_daily_drift_check",):
        from . import drift_reporter as module
        return getattr(module, name)
    
    if name in ("MonitoringError", "DriftDetectionError", "ReferenceStoreError"):
        from . import drift_detector as module
        return getattr(module, name)
    
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


# ── Run validation at import (non-blocking warnings) ─────────
_monitoring_warnings = validate_monitoring_config()
if _monitoring_warnings and os.getenv("MONITORING_STRICT_MODE", "false").lower() == "true":
    import warnings as _warnings
    for w in _monitoring_warnings:
        _warnings.warn(f"Monitoring config: {w}", RuntimeWarning, stacklevel=2)