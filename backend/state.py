"""
backend/state.py

Centralised shared state for the FastAPI application.
Single source of truth for pipeline reference, latest frame,
and SHAP explainer instance.

# FIXED: Thread-safe state access across FastAPI + worker threads
# FIXED: Proper type hints with Any for circular import avoidance
# IMPROVED: Clear reset() method for testing
# FIXED: Uptime calculation with monotonic time
# IMPROVED: Dependency injection ready for testing
"""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field
from typing import Optional, Any, TYPE_CHECKING

from loguru import logger

# Avoid circular imports at runtime
if TYPE_CHECKING:
    from .inference.pipeline import InferencePipeline, FrameResult
    from .inference.explainer import SHAPExplainer
    from .pipeline import PipelineRuntime


@dataclass
class AppState:
    """
    Holds all mutable application state.
    Accessed via the module-level `app_state` singleton.
    
    # IMPROVED: Clear typing with TYPE_CHECKING for IDE support
    # FIXED: Monotonic time for uptime calculation
    """
    # Core components (typed as Any to avoid circular imports)
    pipeline: Optional['InferencePipeline'] = None
    pipeline_runtime: Optional['PipelineRuntime'] = None
    shap_explainer: Optional['SHAPExplainer'] = None
    latest_frame: Optional['FrameResult'] = None
    pipeline_status: str = "stopped"
    pipeline_error: Optional[str] = None
    
    # Configuration (immutable after startup)
    model_path: str = "models/best.pt"
    device: str = "cpu"
    video_source: Any = 0  # int or str
    
    # Internal state
    _start_time: float = field(default_factory=time.monotonic)
    _lock: Any = field(default=None, init=False, repr=False)  # threading.RLock, set in __post_init__

    def __post_init__(self):
        """
        Initialise a process-local lock.

        The inference pipeline now runs in a dedicated background thread, so an
        asyncio.Lock would bind state access to one event loop and break
        cross-thread coordination.
        """
        self._lock = threading.RLock()

    @property
    def uptime_seconds(self) -> float:
        """Seconds since application startup (monotonic time)."""
        return time.monotonic() - self._start_time

    def set_latest_frame(self, frame: Optional['FrameResult']) -> None:
        """Thread-safe update of latest_frame from the pipeline worker."""
        with self._lock:
            self.latest_frame = frame

    def get_latest_frame(self) -> Optional['FrameResult']:
        """Thread-safe read of latest_frame."""
        with self._lock:
            return self.latest_frame

    async def update_latest_frame(self, frame: 'FrameResult') -> None:
        """Backward-compatible async wrapper used by older call sites."""
        self.set_latest_frame(frame)

    async def get_latest_frame_async(self) -> Optional['FrameResult']:
        """Backward-compatible async wrapper for route/test helpers."""
        return self.get_latest_frame()

    def set_pipeline(self, pipeline: Optional['InferencePipeline']) -> None:
        with self._lock:
            self.pipeline = pipeline

    def get_pipeline(self) -> Optional['InferencePipeline']:
        with self._lock:
            return self.pipeline

    def set_pipeline_runtime(self, runtime: Optional['PipelineRuntime']) -> None:
        with self._lock:
            self.pipeline_runtime = runtime

    def get_pipeline_runtime(self) -> Optional['PipelineRuntime']:
        with self._lock:
            return self.pipeline_runtime

    def set_shap_explainer(self, explainer: Optional['SHAPExplainer']) -> None:
        with self._lock:
            self.shap_explainer = explainer

    def get_shap_explainer(self) -> Optional['SHAPExplainer']:
        with self._lock:
            return self.shap_explainer

    def set_pipeline_status(self, status: str, error: Optional[str] = None) -> None:
        with self._lock:
            self.pipeline_status = status
            self.pipeline_error = error

    def get_pipeline_status(self) -> tuple[str, Optional[str]]:
        with self._lock:
            return self.pipeline_status, self.pipeline_error

    @property
    def pipeline_running(self) -> bool:
        with self._lock:
            return self.pipeline is not None and bool(getattr(self.pipeline, "_running", False))

    def reset(self) -> None:
        """
        Reset all mutable fields to defaults.
        Used in tests to prevent state leaking between test cases.
        
        # FIXED: Log reset for debugging unexpected resets in production
        """
        logger.debug("AppState.reset() called — clearing all state")
        with self._lock:
            self.pipeline = None
            self.pipeline_runtime = None
            self.shap_explainer = None
            self.latest_frame = None
            self.pipeline_status = "stopped"
            self.pipeline_error = None
            # Don't reset config fields (model_path, device, video_source)
            self._start_time = time.monotonic()

    def get_diagnostics(self) -> dict:
        """Return state diagnostics for health checks."""
        status, error = self.get_pipeline_status()
        return {
            "pipeline_running": self.pipeline_running,
            "pipeline_status": status,
            "pipeline_error": error,
            "shap_explainer_ready": self.get_shap_explainer() is not None,
            "latest_frame_available": self.get_latest_frame() is not None,
            "uptime_seconds": round(self.uptime_seconds, 1),
            "config": {
                "model_path": self.model_path,
                "device": self.device,
                "video_source": str(self.video_source),
            },
        }


# Module-level singleton
app_state = AppState()


# ── Testing utilities ─────────────────────────────────────────
def get_test_app_state() -> AppState:
    """
    Get a fresh AppState for testing.
    
    Usage in tests:
        def test_something():
            state = get_test_app_state()
            # ... test with isolated state
    """
    return AppState()
