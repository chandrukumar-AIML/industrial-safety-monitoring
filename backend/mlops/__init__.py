"""
backend/mlops/__init__.py

Public API for MLOps and model deployment utilities.

# Usage:
    from backend.mlops import (
        canary_router, evaluate_canary, promote_canary,
        register_model, get_production_model, ModelVersion,
        start_canary_deployment, run_canary_evaluation_loop,
    )
    from backend.mlops import MLOpsError, DeploymentError  # Exceptions

# Example:
    result = await evaluate_canary(deployment_id=5, db_factory=AsyncSessionLocal)
    if result.verdict == EvaluationVerdict.PROMOTE:
        await promote_canary(deployment_id=5, db_factory=AsyncSessionLocal)
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .model_registry import ModelVersion, ModelRegistryClient
    from .canary_router import CanaryRouter, RoutingDecision, ModelVariant, CanaryState
    from .canary_evaluator import EvaluationResult, EvaluationVerdict, evaluate_canary
    from .deployment_manager import DeploymentManager

# ── Explicit public API ──────────────────────────────────────
__all__ = [
    # Core classes
    "ModelVersion",
    "ModelRegistryClient",
    "CanaryRouter",
    "RoutingDecision",
    "ModelVariant",
    "CanaryState",
    "EvaluationResult",
    "EvaluationVerdict",
    "DeploymentManager",
    
    # Functions
    "register_model",
    "get_production_model",
    "get_staging_models",
    "promote_to_production",
    "archive_model",
    "list_all_versions",
    "evaluate_canary",
    "record_canary_metric",
    "start_canary_deployment",
    "promote_canary",
    "rollback_canary",
    "run_canary_evaluation_loop",
    
    # Singletons
    "canary_router",
    "model_registry",
    
    # Exceptions
    "MLOpsError",
    "DeploymentError",
    "ModelRegistryError",
    "CanaryEvaluationError",
    
    # Config helpers
    "get_mlops_config",
    "validate_mlops_config",
]

__version__ = "1.0.0"
__author__ = "Chandrukumar S"
__description__ = "MLOps utilities for model deployment and canary testing"


# ── Config helpers ───────────────────────────────────────────
def get_mlops_config() -> dict:
    """Return current MLOps configuration."""
    from .model_registry import MLFLOW_URI, MODEL_NAME, MAP_GATE
    from .canary_router import CANARY_PCT, CANARY_MIN_FRAMES
    from .canary_evaluator import CONFIDENCE_GAIN, MAX_LATENCY_RATIO, ROLLBACK_CONFIDENCE_DROP
    from .deployment_manager import AUTO_PROMOTE, EVAL_INTERVAL_S
    
    return {
        "mlflow": {
            "tracking_uri": MLFLOW_URI,
            "model_name": MODEL_NAME,
            "map_gate_threshold": MAP_GATE,
        },
        "canary": {
            "traffic_pct": CANARY_PCT,
            "min_frames": CANARY_MIN_FRAMES,
            "confidence_gain_threshold": CONFIDENCE_GAIN,
            "max_latency_ratio": MAX_LATENCY_RATIO,
            "rollback_confidence_drop": ROLLBACK_CONFIDENCE_DROP,
        },
        "deployment": {
            "auto_promote": AUTO_PROMOTE,
            "evaluation_interval_s": EVAL_INTERVAL_S,
        },
    }


def validate_mlops_config() -> list[str]:
    """
    Validate MLOps config at startup.
    Returns list of warnings (empty = OK).
    """
    warnings = []
    
    # MLflow URI
    mlflow_uri = os.getenv("MLFLOW_TRACKING_URI", "sqlite:///mlflow/mlflow.db")
    if not mlflow_uri.startswith(("http://", "https://", "sqlite://", "postgresql://")):
        warnings.append(f"MLFLOW_TRACKING_URI may be invalid: {mlflow_uri}")
    
    # Model name
    model_name = os.getenv("MLFLOW_MODEL_NAME", "")
    if not model_name or not model_name.strip():
        warnings.append("MLFLOW_MODEL_NAME is empty — using default 'ppe-detector'")
    
    # Thresholds
    try:
        map_gate = float(os.getenv("CANARY_MAP_GATE_THRESHOLD", "0.85"))
        if not 0 <= map_gate <= 1:
            warnings.append(f"CANARY_MAP_GATE_THRESHOLD={map_gate} outside 0-1 range")
    except ValueError:
        warnings.append("CANARY_MAP_GATE_THRESHOLD must be a float")
    
    try:
        canary_pct = float(os.getenv("CANARY_TRAFFIC_PCT", "10"))
        if not 0 <= canary_pct <= 100:
            warnings.append(f"CANARY_TRAFFIC_PCT={canary_pct} outside 0-100 range")
    except ValueError:
        warnings.append("CANARY_TRAFFIC_PCT must be a float")
    
    # Auto-promote warning
    if os.getenv("AUTO_PROMOTE_CANARY", "false").lower() == "true":
        warnings.append("AUTO_PROMOTE_CANARY is enabled — ensure thorough testing before production use")
    
    return warnings


# ── Lazy loader for heavy imports ────────────────────────────
def __getattr__(name: str) -> Any:
    """Lazy-load submodules only when accessed."""
    
    if name in ("ModelVersion", "ModelRegistryClient", "model_registry"):
        from . import model_registry as module
        return getattr(module, name)
    
    if name in ("CanaryRouter", "RoutingDecision", "ModelVariant", "CanaryState", "canary_router"):
        from . import canary_router as module
        return getattr(module, name)
    
    if name in ("EvaluationResult", "EvaluationVerdict", "evaluate_canary", "record_canary_metric"):
        from . import canary_evaluator as module
        return getattr(module, name)
    
    if name in ("DeploymentManager", "start_canary_deployment", "promote_canary", "rollback_canary", "run_canary_evaluation_loop"):
        from . import deployment_manager as module
        return getattr(module, name)
    
    if name in ("MLOpsError", "DeploymentError", "ModelRegistryError", "CanaryEvaluationError"):
        from . import model_registry as module
        return getattr(module, name)
    
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


# ── Run validation at import (non-blocking warnings) ─────────
_mlops_warnings = validate_mlops_config()
if _mlops_warnings and os.getenv("MLOPS_STRICT_MODE", "false").lower() == "true":
    import warnings as _warnings
    for w in _mlops_warnings:
        _warnings.warn(f"MLOps config: {w}", RuntimeWarning, stacklevel=2)