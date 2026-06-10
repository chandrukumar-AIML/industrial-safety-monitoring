"""
agent/state.py

TypedDict that defines the complete agent state.
Every node reads from and writes to this shared state object.
LangGraph passes state through the graph immutably —
each node returns a dict of updates, never mutates in-place.

# IMPROVED: Added Required[] for critical fields to catch missing keys early
# IMPROVED: Added Pydantic-style field descriptions for OpenAPI/docs
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
from typing_extensions import TypedDict, Required, NotRequired


class AgentState(TypedDict, total=False):
    """
    Complete state for one safety agent run.
    
    # IMPROVED: Explicit Required/NotRequired for better type checking
    # IMPROVED: Added field-level documentation for maintainability
    """

    # ── Input (always present at graph start) ─────────────────
    run_id: Required[str]  # Unique identifier for this agent run
    violation_event: Required[Dict[str, Any]]  # from pipeline TrackedDetection

    # ── Node outputs (populated progressively) ────────────────
    severity_score: NotRequired[int]  # 1-10, set by ScoreSeverity node
    severity_reason: NotRequired[str]  # LLM-generated reasoning
    worker_history: NotRequired[Dict[str, Any]]  # prior violations for this track_id
    alert_level: NotRequired[str]  # NONE | LOW | MEDIUM | HIGH | CRITICAL
    should_report: NotRequired[bool]  # True if severity >= threshold
    should_alert: NotRequired[bool]  # True if alert_level >= HIGH
    report_id: NotRequired[Optional[int]]  # DB report ID if generated
    report_summary: NotRequired[Optional[str]]  # brief report summary
    alert_sent: NotRequired[bool]  # True if WhatsApp/email sent
    compliance_delta: NotRequired[float]  # change applied to compliance score
    final_status: NotRequired[str]  # COMPLETE | FAILED | SKIPPED | TIMEOUT

    # ── Audit trail (appended by every node) ──────────────────
    trace_steps: NotRequired[List[Dict[str, Any]]]  # audit log entries

    # ── Error handling ────────────────────────────────────────
    error: NotRequired[Optional[str]]  # error message if any node fails

    # ── Dependency injection (for testability) ────────────────
    # IMPROVED: Allow passing db_factory and llm_client via state for mocking
    db_factory: NotRequired[Any]  # AsyncSessionLocal factory
    llm_client: NotRequired[Any]  # Optional pre-initialized LLM client

    # ── PII/Security flags ────────────────────────────────────
    # IMPROVED: Toggle for redacting sensitive fields in logs/traces
    redact_pii: NotRequired[bool]  # Default False; set True for compliance mode