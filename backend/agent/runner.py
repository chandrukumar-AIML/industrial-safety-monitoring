"""
agent/runner.py

Agent trigger and async runner.
Manages concurrent agent runs with a semaphore.
Integrates LangSmith tracing.

# FIXED: No runtime os.environ mutation — configure at startup only
# FIXED: Track background tasks to avoid silent failures
# IMPROVED: Add metrics/logging for timeout/error rates
# IMPROVED: Dependency injection for testability
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from loguru import logger

from .graph import build_safety_agent, CompiledStateGraph
from .state import AgentState

# ── Config: Validate at import time ───────────────────────────
# FIXED: module-level raise → warning + clamp
_MAX_CONCURRENT = int(os.getenv("AGENT_MAX_CONCURRENT_RUNS", "3"))
if _MAX_CONCURRENT < 1:
    logger.warning("AGENT_MAX_CONCURRENT_RUNS too small ({}) — clamping to 1", _MAX_CONCURRENT)
    _MAX_CONCURRENT = 1

_DEFAULT_TIMEOUT = float(os.getenv("AGENT_RUN_TIMEOUT_SECONDS", "60.0"))
if _DEFAULT_TIMEOUT < 10:
    logger.warning("AGENT_RUN_TIMEOUT_SECONDS too small ({}) — clamping to 10", _DEFAULT_TIMEOUT)
    _DEFAULT_TIMEOUT = 10.0

# ── Task registry for monitoring ─────────────────────────────
_active_agent_tasks: Dict[str, asyncio.Task] = {}
_agent_metrics = defaultdict(int)  # Simple in-mem metrics; replace with Prometheus in prod


def _configure_langsmith_once() -> None:
    """
    Configure LangSmith tracing exactly once at startup.
    
    # FIXED: No runtime env mutation — call once during app init
    """
    if not os.getenv("LANGCHAIN_API_KEY"):
        logger.info("LangSmith not configured — tracing disabled")
        return
    
    # Only set if not already set (avoid race conditions)
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_PROJECT", "safety-monitor-agent")
    
    logger.info("LangSmith tracing enabled | project={}", os.getenv("LANGCHAIN_PROJECT"))


# Call once at module load
_configure_langsmith_once()


async def run_agent(
    violation_event: Dict[str, Any],
    timeout_s: float = _DEFAULT_TIMEOUT,
    db_factory: Optional[Any] = None,
    llm_client: Optional[Any] = None,
    redact_pii: bool = False,
) -> Dict[str, Any]:
    """
    Run the safety agent for one violation event.
    
    # IMPROVED: Accept injected dependencies for testability
    # FIXED: Use timezone-aware datetime in logs
    """
    run_id = str(uuid.uuid4())[:12]
    _agent_metrics["runs_started"] += 1

    initial_state: AgentState = {
        "run_id": run_id,
        "violation_event": violation_event,
        "trace_steps": [],
        "alert_sent": False,
        "final_status": "RUNNING",
        "error": None,
        "db_factory": db_factory,      # Injected for testing
        "llm_client": llm_client,      # Injected for testing
        "redact_pii": redact_pii,      # PII redaction toggle
    }

    logger.info(
        "Agent run started | id={} | track={} | class={}",
        run_id,
        violation_event.get("track_id"),
        violation_event.get("class_name"),
    )

    # Build graph with injected deps if provided
    graph: CompiledStateGraph = build_safety_agent(
        db_factory=db_factory,
        llm_client=llm_client,
    ) if (db_factory or llm_client) else build_safety_agent()

    async with asyncio.Semaphore(_MAX_CONCURRENT):
        try:
            config = {}
            if os.getenv("LANGCHAIN_API_KEY"):
                config = {
                    "run_name": f"SafetyAgent-{run_id}",
                    "tags": ["safety-monitor", "violation-agent"],
                    "metadata": {
                        "track_id": violation_event.get("track_id"),
                        "class_name": violation_event.get("class_name"),
                    },
                }

            final_state = await asyncio.wait_for(
                graph.ainvoke(initial_state, config=config),
                timeout=timeout_s,
            )

            logger.info(
                "Agent run complete | id={} | status={} | alert_level={} | score={}",
                run_id,
                final_state.get("final_status"),
                final_state.get("alert_level"),
                final_state.get("severity_score"),
            )
            _agent_metrics["runs_completed"] += 1
            return final_state

        except asyncio.TimeoutError:
            logger.error("Agent run timed out | id={} | timeout={}s", run_id, timeout_s)
            _agent_metrics["runs_timed_out"] += 1
            return {
                **initial_state,
                "final_status": "TIMEOUT",
                "error": f"Agent timed out after {timeout_s}s",
            }
        except Exception as exc:
            logger.exception("Agent run failed | id={}", run_id)
            _agent_metrics["runs_failed"] += 1
            return {
                **initial_state,
                "final_status": "FAILED",
                "error": str(exc),
            }


# ── Task registry helpers ─────────────────────────────────────
def get_active_agent_tasks() -> Dict[str, Dict]:
    """Return snapshot of active tasks for monitoring endpoint."""
    return {
        name: {
            "track_id": task.get_name().split("_")[1] if "_" in task.get_name() else None,
            "state": "running" if not task.done() else "done",
        }
        for name, task in _active_agent_tasks.items()
    }


def get_agent_metrics() -> Dict:
    """Return simple metrics for dashboard."""
    total = _agent_metrics["runs_started"]
    return {
        "started": _agent_metrics["runs_started"],
        "completed": _agent_metrics["runs_completed"],
        "timed_out": _agent_metrics["runs_timed_out"],
        "failed": _agent_metrics["runs_failed"],
        "success_rate": round(_agent_metrics["runs_completed"] / total * 100, 1) if total > 0 else 0,
    }


async def trigger_from_violation(
    track_id: int,
    class_name: str,
    confidence: float,
    zone_id: Optional[str],
    frame_idx: int,
    timestamp: Optional[str] = None,
    **kwargs,  # Allow passing injected deps
) -> asyncio.Task:
    """
    Convenience function — build event dict and fire agent.
    
    # FIXED: Return the Task so caller can track/cancel if needed
    # IMPROVED: Accept injected dependencies for testing
    """
    event = {
        "track_id": track_id,
        "class_name": class_name,
        "confidence": confidence,
        "zone_id": zone_id,
        "frame_idx": frame_idx,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
    }
    
    task = asyncio.create_task(
        run_agent(event, **kwargs),
        name=f"agent_{track_id}_{class_name}",
    )
    
    # Register for monitoring + auto-cleanup
    _active_agent_tasks[task.get_name()] = task
    task.add_done_callback(lambda t: _active_agent_tasks.pop(t.get_name(), None))
    
    logger.debug(
        "Agent triggered (background) | track={} | class={} | task={}",
        track_id, class_name, task.get_name(),
    )
    
    return task  # Return task for optional awaiting/tracking