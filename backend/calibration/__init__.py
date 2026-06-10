"""
backend/calibration/__init__.py

Public API for camera calibration utilities.

# Usage:
    from backend.calibration import CameraCalibration, calibrate_camera
    from backend.calibration import CalibrationError, CalibrationNotFoundError

# Example:
    cal = CameraCalibration.load(camera_id="cam-01")
    if cal:
        distance_m = cal.real_distance_metres(px1, py1, px2, py2)
    else:
        # Fallback to pixel distance
        distance_px = pixel_distance(px1, py1, px2, py2)
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .calibrator import CameraCalibration
    from .calibrate_camera import calibrate as calibrate_camera

# ── Explicit public API ──────────────────────────────────────
__all__ = [
    # Core classes
    "CameraCalibration",
    
    # Functions
    "calibrate_camera",
    "pixel_distance",
    
    # Exceptions
    "CalibrationError",
    "CalibrationNotFoundError",
    "CalibrationValidationError",
    
    # Config
    "get_calibration_config",
    "CALIBRATION_PATH",
    "CRITICAL_M",
    "WARNING_M",
]

__version__ = "1.0.0"
__description__ = "Camera calibration utilities for pixel→metre conversion"


# ── Re-export constants from calibrator ───────────────────────
def __getattr__(name: str) -> Any:
    """Lazy-load to avoid cv2/numpy import on package load."""
    
    if name in ("CameraCalibration", "CALIBRATION_PATH", "CRITICAL_M", "WARNING_M"):
        from . import calibrator
        return getattr(calibrator, name)
    
    if name in ("calibrate_camera",):
        from . import calibrate_camera
        return getattr(calibrate_camera, name)
    
    if name == "pixel_distance":
        from . import calibrator
        return getattr(calibrator, name)
    
    if name in ("CalibrationError", "CalibrationNotFoundError", "CalibrationValidationError"):
        from . import calibrator
        return getattr(calibrator, name)
    
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


# ── Config helper ────────────────────────────────────────────
def get_calibration_config() -> dict:
    """Return current calibration configuration."""
    from .calibrator import CALIBRATION_PATH, CRITICAL_M, WARNING_M
    return {
        "calibration_path": str(CALIBRATION_PATH),
        "proximity_thresholds": {
            "critical_m": CRITICAL_M,
            "warning_m": WARNING_M,
        },
    }