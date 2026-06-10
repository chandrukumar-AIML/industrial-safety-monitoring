"""
backend/inference/__init__.py

Public API for the inference pipeline components.

# Usage:
    from backend.inference import (
        PPEDetector, ByteTracker, TrackedDetection,
        FireDetector, FireDetection, FireHeatmap,
        PoseDetector, PoseLandmarks,
        ProximityEngine, ProximityAlert,
        HeatmapGenerator, ZoneRisk,
        LightEnhancer, EnhancementStats,
        SHAPExplainer,
        load_zones, ZoneRegistrar,
    )
    from backend.inference import InferenceError, ModelLoadError  # Exceptions

# Example:
    detector = PPEDetector("models/best.pt", device="cuda")
    results = detector.predict(frame_bgr)
    tracked = tracker.update(results, frame_idx=42)
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Type hints only — no runtime import cost
    from .detector import PPEDetector
    from .tracker import ByteTracker, TrackedDetection, TrackHistory
    from .fire_detector import FireDetector, FireDetection, FireHeatmap
    from .pose_detector import PoseDetector, PoseLandmarks
    from .proximity_engine import ProximityEngine, ProximityAlert
    from .heatmap import HeatmapGenerator, ZoneRisk
    from .light_enhancer import LightEnhancer, EnhancementStats, LightMode
    from .explainer import SHAPExplainer
    from .zones import load_zones, ZoneRegistrar
    from .machinery_detector import MachineryDetector, MachineryDetection

# ── Explicit public API ──────────────────────────────────────
__all__ = [
    # Core detectors
    "PPEDetector",
    "FireDetector",
    "MachineryDetector",
    "PoseDetector",
    
    # Tracking & data classes
    "ByteTracker",
    "TrackedDetection",
    "TrackHistory",
    "FireDetection",
    "FireHeatmap",
    "PoseLandmarks",
    "MachineryDetection",
    
    # Analysis engines
    "ProximityEngine",
    "ProximityAlert",
    "HeatmapGenerator",
    "ZoneRisk",
    "LightEnhancer",
    "EnhancementStats",
    "LightMode",
    
    # Explainability
    "SHAPExplainer",
    
    # Zone management
    "load_zones",
    "ZoneRegistrar",
    
    # Exceptions
    "InferenceError",
    "ModelLoadError",
    "InferenceRuntimeError",
    
    # Config helpers
    "get_inference_config",
    "validate_inference_config",
]

__version__ = "1.0.0"
__author__ = "Chandrukumar S"
__description__ = "Computer vision inference pipeline for Industrial Safety Monitor"


# ── Config helpers ───────────────────────────────────────────
def get_inference_config() -> dict:
    """Return current inference system configuration."""
    from .detector import _MIN_THRESHOLD, _MAX_THRESHOLD, _MIN_IMGSZ
    from .fire_detector import FIRE_CONF_THRESH, SMOKE_CONF_THRESH
    from .heatmap import HeatmapGenerator
    from .light_enhancer import ENABLED as LIGHT_ENABLED, DARK_THRESHOLD
    
    return {
        "model": {
            "conf_threshold_range": (_MIN_THRESHOLD, _MAX_THRESHOLD),
            "min_imgsz": _MIN_IMGSZ,
        },
        "fire_detection": {
            "fire_conf_threshold": FIRE_CONF_THRESH,
            "smoke_conf_threshold": SMOKE_CONF_THRESH,
        },
        "heatmap": {
            "default_risk_thresholds": HeatmapGenerator.DEFAULT_RISK_THRESHOLDS,
        },
        "light_enhancement": {
            "enabled": LIGHT_ENABLED,
            "dark_threshold": DARK_THRESHOLD,
        },
        "devices": {
            "available": _get_available_devices(),
            "default": os.getenv("DEVICE", "cpu"),
        },
    }


def _get_available_devices() -> list[str]:
    """Detect available inference devices."""
    devices = ["cpu"]
    try:
        import torch
        if torch.cuda.is_available():
            devices.append(f"cuda:{torch.cuda.current_device()}")
            devices.append("cuda")
        if torch.backends.mps.is_available():
            devices.append("mps")
    except ImportError:
        pass
    return devices


def validate_inference_config() -> list[str]:
    """
    Validate inference config at startup.
    Returns list of warnings (empty = OK).
    """
    warnings = []
    
    # Check model paths
    model_paths = [
        os.getenv("MODEL_PATH", "models/best.pt"),
        os.getenv("FIRE_MODEL_PATH", "models/fire_best.pt"),
        os.getenv("MACHINERY_MODEL_PATH", "models/machinery_best.pt"),
    ]
    for path in model_paths:
        if not os.path.exists(path):
            warnings.append(f"Model not found: {path} — inference will fail until model is available")
    
    # Check device config
    device = os.getenv("DEVICE", "cpu").lower()
    if device.startswith("cuda"):
        try:
            import torch
            if not torch.cuda.is_available():
                warnings.append(f"DEVICE={device} but CUDA not available — falling back to CPU")
        except ImportError:
            warnings.append("PyTorch not installed — CUDA/MPS devices unavailable")
    
    # Check threshold configs
    try:
        conf = float(os.getenv("CONFIDENCE_THRESHOLD", "0.35"))
        if not 0 <= conf <= 1:
            warnings.append(f"CONFIDENCE_THRESHOLD={conf} outside 0-1 range")
    except ValueError:
        warnings.append("CONFIDENCE_THRESHOLD must be a float")
    
    return warnings


# ── Lazy loader for heavy imports ────────────────────────────
def __getattr__(name: str) -> Any:
    """Lazy-load submodules only when accessed."""
    
    if name in ("PPEDetector",):
        from . import detector as module
        return getattr(module, name)
    
    if name in ("ByteTracker", "TrackedDetection", "TrackHistory"):
        from . import tracker as module
        return getattr(module, name)
    
    if name in ("FireDetector", "FireDetection", "FireHeatmap"):
        from . import fire_detector as module
        return getattr(module, name)
    
    if name in ("MachineryDetector", "MachineryDetection"):
        from . import machinery_detector as module
        return getattr(module, name)
    
    if name in ("PoseDetector", "PoseLandmarks"):
        from . import pose_detector as module
        return getattr(module, name)
    
    if name in ("ProximityEngine", "ProximityAlert"):
        from . import proximity_engine as module
        return getattr(module, name)
    
    if name in ("HeatmapGenerator", "ZoneRisk"):
        from . import heatmap as module
        return getattr(module, name)
    
    if name in ("LightEnhancer", "EnhancementStats", "LightMode"):
        from . import light_enhancer as module
        return getattr(module, name)
    
    if name in ("SHAPExplainer",):
        from . import explainer as module
        return getattr(module, name)
    
    if name in ("load_zones", "ZoneRegistrar"):
        from . import zones as module
        return getattr(module, name)
    
    if name in ("InferenceError", "ModelLoadError", "InferenceRuntimeError"):
        from . import detector as module
        return getattr(module, name)
    
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


# ── Run validation at import (non-blocking warnings) ─────────
_inference_warnings = validate_inference_config()
if _inference_warnings and os.getenv("INFERENCE_STRICT_MODE", "false").lower() == "true":
    import warnings as _warnings
    for w in _inference_warnings:
        _warnings.warn(f"Inference config: {w}", RuntimeWarning, stacklevel=2)