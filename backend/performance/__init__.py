"""
backend/performance/__init__.py

Public API for performance optimization utilities.

# Usage:
    from backend.performance import (
        batch_writer, BatchWriter, ViolationRecord,
        get_ws_manager, OptimisedConnectionManager,
        run_load_test, get_performance_config,
    )
    from backend.performance import PerformanceError, BatchWriteError  # Exceptions

# Example:
    writer = BatchWriter()
    await writer.start(db_factory)
    writer.enqueue(violation_record)
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .batch_writer import BatchWriter, ViolationRecord
    from .ws_optimizer import OptimisedConnectionManager
    from .load_test import run_load_test

# ── Explicit public API ──────────────────────────────────────
__all__ = [
    # Core classes
    "BatchWriter",
    "ViolationRecord",
    "OptimisedConnectionManager",
    
    # Functions
    "run_load_test",
    
    # Singletons
    "batch_writer",
    "ws_manager",
    
    # Exceptions
    "PerformanceError",
    "BatchWriteError",
    "WebSocketError",
    
    # Config helpers
    "get_performance_config",
    "validate_performance_config",
]

__version__ = "1.0.0"
__author__ = "Chandrukumar S"
__description__ = "Performance optimization utilities for Industrial Safety Monitor"


# ── Config helpers ───────────────────────────────────────────
def get_performance_config() -> dict:
    """Return current performance configuration."""
    from .batch_writer import BATCH_INTERVAL_S, BATCH_MAX_SIZE
    from .ws_optimizer import WS_CONCURRENCY, CLIENT_FPS_CAP, PRIORITY_TYPES
    
    return {
        "batch_writer": {
            "interval_s": BATCH_INTERVAL_S,
            "max_size": BATCH_MAX_SIZE,
        },
        "websocket": {
            "concurrency": WS_CONCURRENCY,
            "client_fps_cap": CLIENT_FPS_CAP,
            "priority_types": list(PRIORITY_TYPES),
        },
        "load_testing": {
            "default_users": int(os.getenv("LOAD_TEST_USERS", "50")),
            "default_spawn_rate": int(os.getenv("LOAD_TEST_SPAWN_RATE", "5")),
            "default_run_time_s": int(os.getenv("LOAD_TEST_RUN_TIME_S", "60")),
        },
    }


def validate_performance_config() -> list[str]:
    """
    Validate performance config at startup.
    Returns list of warnings (empty = OK).
    """
    warnings = []
    
    # Batch writer config
    try:
        interval = float(os.getenv("BATCH_WRITE_INTERVAL_S", "30"))
        if not 1 <= interval <= 300:
            warnings.append(f"BATCH_WRITE_INTERVAL_S={interval} outside 1-300 range")
    except ValueError:
        warnings.append("BATCH_WRITE_INTERVAL_S must be a float")
    
    try:
        batch_size = int(os.getenv("BATCH_WRITE_MAX_SIZE", "500"))
        if not 100 <= batch_size <= 5000:
            warnings.append(f"BATCH_WRITE_MAX_SIZE={batch_size} outside 100-5000 range")
    except ValueError:
        warnings.append("BATCH_WRITE_MAX_SIZE must be an integer")
    
    # WebSocket config
    try:
        concurrency = int(os.getenv("WS_CONCURRENCY", "50"))
        if not 10 <= concurrency <= 200:
            warnings.append(f"WS_CONCURRENCY={concurrency} outside 10-200 range")
    except ValueError:
        warnings.append("WS_CONCURRENCY must be an integer")
    
    try:
        fps_cap = int(os.getenv("CLIENT_FPS_CAP", "25"))
        if not 1 <= fps_cap <= 60:
            warnings.append(f"CLIENT_FPS_CAP={fps_cap} outside 1-60 range")
    except ValueError:
        warnings.append("CLIENT_FPS_CAP must be an integer")
    
    return warnings


# ── Lazy loader for heavy imports ────────────────────────────
def __getattr__(name: str) -> Any:
    """Lazy-load submodules only when accessed."""
    
    if name in ("BatchWriter", "ViolationRecord", "batch_writer"):
        from . import batch_writer as module
        return getattr(module, name)
    
    if name in ("OptimisedConnectionManager", "ws_manager"):
        from . import ws_optimizer as module
        return getattr(module, name)
    
    if name in ("run_load_test",):
        from . import load_test as module
        return getattr(module, name)
    
    if name in ("PerformanceError", "BatchWriteError", "WebSocketError"):
        from . import batch_writer as module
        return getattr(module, name)
    
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


# ── Run validation at import (non-blocking warnings) ─────────
_perf_warnings = validate_performance_config()
if _perf_warnings and os.getenv("PERF_STRICT_MODE", "false").lower() == "true":
    import warnings as _warnings
    for w in _perf_warnings:
        _warnings.warn(f"Performance config: {w}", RuntimeWarning, stacklevel=2)