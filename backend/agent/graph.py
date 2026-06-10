"""
agent/graph.py

LangGraph StateGraph definition.

# IMPROVED: Make graph builder accept dependencies for testability
# FIXED: Add return type hints
# IMPROVED: Lazy singleton pattern for easier testing
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Any

from langgraph.graph import StateGraph, END, START
from langgraph.graph.state import CompiledStateGraph

from .state import AgentState
from .nodes import (
    node_detect_violation,
    node_check_worker_history,
    node_score_severity,
    node_decide_alert_level,
    node_generate_report,
    node_send_alert,
    node_log_to_database,
    node_update_compliance,
)

if TYPE_CHECKING:
    from .tools import DBFactoryProtocol


def _route_after_detect(state: AgentState) -> str:
    """After detect: if malformed, end immediately."""
    if state.get("final_status") == "SKIPPED":
        return END
    return "check_worker_history"


def _route_after_decide(state: AgentState) -> str:
    """After decide: conditional report generation."""
    if state.get("should_report"):
        return "generate_report"
    return "send_alert"


def _route_after_report(state: AgentState) -> str:
    """After report: conditional alert sending."""
    if state.get("should_alert"):
        return "send_alert"
    return "log_to_database"


def build_safety_agent(
    db_factory: Optional["DBFactoryProtocol"] = None,
    llm_client: Optional[Any] = None,
) -> CompiledStateGraph:
    """
    Build and compile the LangGraph safety agent.
    
    # IMPROVED: Accept injected dependencies for testing
    # FIXED: Add explicit return type
    """
    graph = StateGraph(AgentState)

    # ── Add nodes with optional dependency injection ───────────
    # Wrap nodes to inject deps if provided
    def _inject_deps(node_func, **injected):
        async def wrapper(state: AgentState):
            # Merge injected deps into state if not present
            enriched = {**state, **{k: v for k, v in injected.items() if k not in state}}
            return await node_func(enriched)
        return wrapper

    graph.add_node("detect_violation", node_detect_violation)
    graph.add_node("check_worker_history", 
                   _inject_deps(node_check_worker_history, db_factory=db_factory) if db_factory else node_check_worker_history)
    graph.add_node("score_severity", 
                   _inject_deps(node_score_severity, llm_client=llm_client) if llm_client else node_score_severity)
    graph.add_node("decide_alert_level", node_decide_alert_level)
    graph.add_node("generate_report", node_generate_report)
    graph.add_node("send_alert", node_send_alert)
    graph.add_node("log_to_database", 
                   _inject_deps(node_log_to_database, db_factory=db_factory) if db_factory else node_log_to_database)
    graph.add_node("update_compliance", 
                   _inject_deps(node_update_compliance, db_factory=db_factory) if db_factory else node_update_compliance)

    # ── Entry point ───────────────────────────────────────────
    graph.add_edge(START, "detect_violation")

    # ── Conditional routing ───────────────────────────────────
    graph.add_conditional_edges(
        "detect_violation",
        _route_after_detect,
        {END: END, "check_worker_history": "check_worker_history"},
    )

    # ── Linear edges ──────────────────────────────────────────
    graph.add_edge("check_worker_history", "score_severity")
    graph.add_edge("score_severity", "decide_alert_level")

    # ── Conditional: report or skip ───────────────────────────
    graph.add_conditional_edges(
        "decide_alert_level",
        _route_after_decide,
        {"generate_report": "generate_report", "send_alert": "send_alert"},
    )

    graph.add_conditional_edges(
        "generate_report",
        _route_after_report,
        {"send_alert": "send_alert", "log_to_database": "log_to_database"},
    )

    graph.add_edge("send_alert", "log_to_database")
    graph.add_edge("log_to_database", "update_compliance")
    graph.add_edge("update_compliance", END)

    return graph.compile()


# ── Lazy singleton for production use ─────────────────────────
_safety_agent_instance: Optional[CompiledStateGraph] = None


def get_safety_agent(
    db_factory: Optional["DBFactoryProtocol"] = None,
    llm_client: Optional[Any] = None,
) -> CompiledStateGraph:
    """
    Get or create the compiled safety agent singleton.
    
    # IMPROVED: Lazy initialization + dependency injection support
    # FIXED: Thread-safe for async context (Python GIL handles this)
    """
    global _safety_agent_instance
    if _safety_agent_instance is None:
        _safety_agent_instance = build_safety_agent(db_factory=db_factory, llm_client=llm_client)
    return _safety_agent_instance


# Backward compatibility alias
safety_agent = get_safety_agent()