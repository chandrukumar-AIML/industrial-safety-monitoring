"""
backend/agent/__init__.py

Public API for the safety monitoring agent.

This module defines what external code can import from the agent package.
All heavy imports are lazy-loaded to keep app startup fast.

# Usage:
    from backend.agent import run_agent, trigger_from_violation, get_agent_metrics
    from backend.agent import AgentState  # For type hints
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Dict, Optional

# ── Lazy imports: only load when actually used ─────────────────
# This keeps app startup fast (<100ms) even with heavy deps like LangGraph/Ollama

if TYPE_CHECKING:
    # For type hints only — not imported at runtime
    from .state import AgentState
    from .runner import run_agent, trigger_from_violation, get_agent_metrics, get_active_agent_tasks
    from .graph import build_safety_agent, get_safety_agent
    from .tools import (
        get_worker_violation_history,
        get_zone_info,
        update_compliance_score,
        log_agent_run,
        DBFactoryProtocol,
    )

# ── Public API: What we explicitly export ─────────────────────
__all__ = [
    # Core runtime functions
    "run_agent",
    "trigger_from_violation",
    
    # Monitoring / ops
    "get_agent_metrics",
    "get_active_agent_tasks",
    
    # Graph / testing
    "build_safety_agent",
    "get_safety_agent",
    
    # Types (for type hints in other modules)
    "AgentState",
    
    # DB tools (for direct use in tests or custom workflows)
    "get_worker_violation_history",
    "get_zone_info",
    "update_compliance_score",
    "log_agent_run",
    "DBFactoryProtocol",
]

# ── Package metadata ──────────────────────────────────────────
__version__ = "1.2.0"
__author__ = "Chandrukumar S"
__description__ = "LangGraph-based safety violation agent for industrial monitoring"

# ── Config validation at package load time ────────────────────
def _validate_config() -> None:
    """
    Validate critical env vars when package is first imported.
    Fail fast if misconfigured — better than runtime surprises.
    """
    errors = []
    
    # LLM config
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    if not ollama_url.startswith(("http://", "https://")):
        errors.append(f"OLLAMA_BASE_URL must be a valid URL, got: {ollama_url}")
    
    # Severity threshold
    try:
        threshold = int(os.getenv("AGENT_SEVERITY_THRESHOLD", "5"))
        if not 1 <= threshold <= 10:
            errors.append(f"AGENT_SEVERITY_THRESHOLD must be 1-10, got: {threshold}")
    except ValueError:
        errors.append("AGENT_SEVERITY_THRESHOLD must be an integer")
    
    # Concurrency
    try:
        concurrent = int(os.getenv("AGENT_MAX_CONCURRENT_RUNS", "3"))
        if concurrent < 1:
            errors.append(f"AGENT_MAX_CONCURRENT_RUNS must be >= 1, got: {concurrent}")
    except ValueError:
        errors.append("AGENT_MAX_CONCURRENT_RUNS must be an integer")
    
    if errors:
        raise RuntimeError(
            "Agent configuration errors:\n  • " + "\n  • ".join(errors)
        )


# Run validation once at import time
_validate_config()

# ── Lazy loader helper ────────────────────────────────────────
def __getattr__(name: str) -> Any:
    """
    Lazy-load submodules only when accessed.
    
    This avoids importing heavy deps (LangGraph, Ollama, SQLAlchemy)
    until they're actually needed — critical for fast API startup.
    
    # Example:
        from backend.agent import run_agent  # Triggers import here
    """
    if name in ("run_agent", "trigger_from_violation", "get_agent_metrics", "get_active_agent_tasks"):
        from . import runner
        return getattr(runner, name)
    
    if name in ("build_safety_agent", "get_safety_agent"):
        from . import graph
        return getattr(graph, name)
    
    if name == "AgentState":
        from . import state
        return getattr(state, name)
    
    if name in (
        "get_worker_violation_history",
        "get_zone_info",
        "update_compliance_score",
        "log_agent_run",
        "DBFactoryProtocol",
    ):
        from . import tools
        return getattr(tools, name)
    
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


# ── Convenience: One-liner agent trigger for external callers ─
async def process_violation(
    track_id: int,
    class_name: str,
    confidence: float,
    zone_id: Optional[str] = None,
    frame_idx: int = 0,
    **kwargs,
) -> Dict[str, Any]:
    """
    High-level convenience function — trigger agent and wait for result.
    
    Use this when you need the final state (not fire-and-forget).
    
    Args:
        track_id, class_name, confidence, zone_id, frame_idx: Violation details
        **kwargs: Passed to run_agent (db_factory, llm_client, timeout_s, etc.)
    
    Returns:
        Final AgentState dict with alert_level, report_id, etc.
    """
    from .runner import run_agent
    
    event = {
        "track_id": track_id,
        "class_name": class_name,
        "confidence": confidence,
        "zone_id": zone_id,
        "frame_idx": frame_idx,
    }
    return await run_agent(event, **kwargs)


# Add to __all__ for explicit export
__all__.append("process_violation")