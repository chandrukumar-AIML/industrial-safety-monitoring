"""
backend/cameras/__init__.py

Public API for the camera management system.

# Usage:
    from backend.cameras import (
        stream_manager, CameraProcess, CameraConfig,
        start_cameras, stop_cameras, get_camera_health,
    )
    from backend.cameras import CameraError, CameraNotFoundError  # Exceptions

# Example:
    await stream_manager.start(db_factory=AsyncSessionLocal)
    frames = stream_manager.get_all_latest_frames()
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Type hints only — no runtime import cost
    from .stream_manager import StreamManager
    from .camera_process import CameraProcess, CameraFrameResult, CameraHealthEvent
    from .registry import CameraConfig
    from .health_monitor import CameraHealthMonitor, HealthMetrics

# ── Explicit public API ──────────────────────────────────────
__all__ = [
    # Core classes
    "StreamManager",
    "CameraProcess",
    "CameraConfig",
    "CameraHealthMonitor",
    
    # Data classes
    "CameraFrameResult",
    "CameraHealthEvent",
    "HealthMetrics",
    
    # Singleton instances
    "stream_manager",
    "health_monitor",
    
    # Exceptions
    "CameraError",
    "CameraNotFoundError",
    "CameraConnectionError",
    "CameraLimitError",
    
    # Convenience functions
    "start_cameras",
    "stop_cameras",
    "get_camera_health",
    "get_camera_config",
    
    # Config helpers
    "get_cameras_config",
    "validate_cameras_config",
]

__version__ = "1.0.0"
__author__ = "Chandrukumar S"
__description__ = "Multi-camera stream management for Industrial Safety Monitor"


# ── Config helpers ───────────────────────────────────────────
def get_cameras_config() -> dict:
    """Return current camera system configuration."""
    from .stream_manager import MODEL_PATH, DEVICE, FRAME_SKIP, STATS_FLUSH, HEALTH_INT
    from .camera_process import (
        _RECONNECT_BASE, _RECONNECT_MAX, _MAX_ATTEMPTS, _QUEUE_SIZE,
    )
    from .registry import MAX_CAMERAS
    
    return {
        "model": {
            "path": MODEL_PATH,
            "device": DEVICE,
        },
        "inference": {
            "frame_skip": FRAME_SKIP,
            "queue_size": _QUEUE_SIZE,
        },
        "reconnect": {
            "base_delay_s": _RECONNECT_BASE,
            "max_delay_s": _RECONNECT_MAX,
            "max_attempts": _MAX_ATTEMPTS,
        },
        "monitoring": {
            "stats_flush_interval_s": STATS_FLUSH,
            "health_check_interval_s": HEALTH_INT,
        },
        "limits": {
            "max_cameras": MAX_CAMERAS,
        },
    }


def validate_cameras_config() -> list[str]:
    """
    Validate camera config at startup.
    Returns list of warnings (empty = OK).
    """
    warnings = []
    
    # Check model path
    model_path = os.getenv("MODEL_PATH", "models/best.pt")
    if not os.path.exists(model_path):
        warnings.append(f"Model not found at {model_path} — inference will fail")
    
    # Check device
    device = os.getenv("DEVICE", "cpu").lower()
    if device == "cuda":
        try:
            import torch
            if not torch.cuda.is_available():
                warnings.append("DEVICE=cuda but CUDA not available — falling back to CPU")
        except ImportError:
            warnings.append("PyTorch not installed — CUDA device unavailable")
    
    # Check frame skip
    try:
        frame_skip = int(os.getenv("FRAME_SKIP", "2"))
        if not 1 <= frame_skip <= 10:
            warnings.append(f"FRAME_SKIP={frame_skip} outside recommended range 1-10")
    except ValueError:
        warnings.append("FRAME_SKIP must be an integer")
    
    # Check max cameras vs system resources
    max_cams = int(os.getenv("MAX_CAMERAS", "10"))
    if max_cams > 16:
        warnings.append(f"MAX_CAMERAS={max_cams} — ensure sufficient CPU/RAM for multi-process inference")
    
    return warnings


# ── Lazy loader for heavy imports ────────────────────────────
def __getattr__(name: str) -> Any:
    """Lazy-load submodules only when accessed."""
    
    if name in ("StreamManager", "stream_manager"):
        from . import stream_manager as module
        return getattr(module, name)
    
    if name in ("CameraProcess", "CameraFrameResult", "CameraHealthEvent"):
        from . import camera_process as module
        return getattr(module, name)
    
    if name in ("CameraConfig",):
        from . import registry as module
        return getattr(module, name)
    
    if name in ("CameraHealthMonitor", "HealthMetrics", "health_monitor"):
        from . import health_monitor as module
        return getattr(module, name)
    
    if name in ("CameraError", "CameraNotFoundError", "CameraConnectionError", "CameraLimitError"):
        from . import health_monitor as module
        return getattr(module, name)
    
    if name in ("start_cameras", "stop_cameras", "get_camera_health", "get_camera_config"):
        from . import health_monitor as module
        return getattr(module, name)
    
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


# ── Run validation at import (non-blocking warnings) ─────────
_camera_warnings = validate_cameras_config()
if _camera_warnings and os.getenv("CAMERAS_STRICT_MODE", "false").lower() == "true":
    import warnings as _warnings
    for w in _camera_warnings:
        _warnings.warn(f"Cameras config: {w}", RuntimeWarning, stacklevel=2)


# ── Convenience wrappers ─────────────────────────────────────
async def start_cameras(db_factory) -> None:
    """Start the stream manager with all active cameras."""
    from .stream_manager import stream_manager
    await stream_manager.start(db_factory)


async def stop_cameras() -> None:
    """Stop all camera processes gracefully."""
    from .stream_manager import stream_manager
    await stream_manager.stop()


def get_camera_health(camera_id: str) -> dict:
    """Get health metrics for a specific camera."""
    from .health_monitor import health_monitor
    return health_monitor.get_camera_health(camera_id)


def get_camera_config(camera_id: str) -> dict:
    """Get runtime config for a specific camera."""
    from .registry import get_camera
    # Note: Requires db_factory — return empty if not available
    return {}  # Placeholder — actual impl needs DB access