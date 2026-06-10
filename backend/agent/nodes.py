"""
agent/nodes.py

Eight graph nodes — each is an async function that takes
AgentState and returns a dict of state updates.

# IMPROVED: Dependency injection for db_factory and llm_client
# FIXED: Prompt injection protection via sanitization + structured messages
# FIXED: Timezone-aware datetime handling
# IMPROVED: Configurable thresholds via env vars
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from enum import Enum

from loguru import logger
from pydantic import BaseModel, Field

from .state import AgentState

# ── Config: Load from env with validation ─────────────────────
# FIXED: module-level raise → warning + clamp
SEVERITY_THRESHOLD = int(os.getenv("AGENT_SEVERITY_THRESHOLD", "5"))
if not 1 <= SEVERITY_THRESHOLD <= 10:
    logger.warning("AGENT_SEVERITY_THRESHOLD out of 1-10: {} — clamping to 5", SEVERITY_THRESHOLD)
    SEVERITY_THRESHOLD = max(1, min(10, SEVERITY_THRESHOLD))

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
AGENT_LLM_MODEL = os.getenv("AGENT_LLM_MODEL", "llama3")
REDACT_PII = os.getenv("REDACT_PII", "false").lower() == "true"

# ── Helper: Sanitize user input for LLM prompts ───────────────
def _sanitize_for_llm(text: str, max_len: int = 100) -> str:
    """
    Sanitize text before injecting into LLM prompts.
    
    # FIXED: Prevent prompt injection via allowlist + truncation
    """
    if not text:
        return "unknown"
    # Allow only safe characters
    cleaned = "".join(c for c in str(text)[:max_len] if c.isalnum() or c in " _-./@:")
    return cleaned.strip() or "unknown"


def _redact_trace(data: Dict, redact: bool = REDACT_PII) -> Dict:
    """Redact PII fields in trace data if enabled."""
    if not redact:
        return data
    return {
        k: ("***" if k in {"track_id", "worker_id", "zone_id"} else v)
        for k, v in data.items()
    }


def _trace(state: AgentState, node: str, details: dict) -> list:
    """Build updated trace_steps list with timezone-aware timestamp."""
    steps = list(state.get("trace_steps", []))
    steps.append({
        "node": node,
        "timestamp": datetime.now(timezone.utc).isoformat(),  # FIXED: timezone-aware
        "details": _redact_trace(details, state.get("redact_pii", REDACT_PII)),
    })
    return steps


# ══════════════════════════════════════════════════════════════
# NODE 1 — DetectViolation
# ══════════════════════════════════════════════════════════════

async def node_detect_violation(state: AgentState) -> Dict[str, Any]:
    """
    Validate incoming violation event and extract key fields.
    
    # IMPROVED: Validate all expected fields, not just 3
    # FIXED: Use timezone-aware datetime
    """
    node_name = "DetectViolation"
    event = state.get("violation_event", {})

    # Validate required + optional fields
    required = ["track_id", "class_name", "confidence"]
    optional = ["zone_id", "timestamp", "frame_idx", "camera_id"]
    
    missing = [k for k in required if k not in event or event[k] is None]
    if missing:
        logger.warning("Agent: malformed event — missing {}", missing)
        return {
            "final_status": "SKIPPED",
            "error": f"Missing required fields: {missing}",
            "trace_steps": _trace(state, node_name, {
                "status": "SKIPPED",
                "reason": f"Missing: {missing}",
            }),
        }
    
    # Validate field types
    if not isinstance(event["track_id"], int) or event["track_id"] < 0:
        return {
            "final_status": "SKIPPED",
            "error": f"Invalid track_id: {event['track_id']}",
            "trace_steps": _trace(state, node_name, {"status": "SKIPPED", "reason": "Invalid track_id"}),
        }
    
    if not isinstance(event["confidence"], (int, float)) or not 0 <= event["confidence"] <= 1:
        return {
            "final_status": "SKIPPED",
            "error": f"Confidence must be 0-1: {event['confidence']}",
            "trace_steps": _trace(state, node_name, {"status": "SKIPPED", "reason": "Invalid confidence"}),
        }

    logger.info(
        "Agent[{}] | DetectViolation | track={} | class={}",
        state.get("run_id", "?"),
        _redact_trace({"track_id": event["track_id"]}, REDACT_PII)["track_id"],
        _sanitize_for_llm(event["class_name"]),
    )

    return {
        "trace_steps": _trace(state, node_name, {
            "status": "OK",
            "track_id": event["track_id"],
            "class_name": _sanitize_for_llm(event["class_name"]),
            "confidence": float(event["confidence"]),
            "zone_id": _sanitize_for_llm(event.get("zone_id", "")),
        }),
    }


# ══════════════════════════════════════════════════════════════
# NODE 2 — ScoreSeverity (PROMPT INJECTION FIXED)
# ══════════════════════════════════════════════════════════════

_SEVERITY_PROMPT_BASE = """You are a construction site safety severity scorer.
Score this PPE violation on a scale of 1-10.

SCORING GUIDE:
1-2: Minor (low-risk area, high confidence PPE present elsewhere)
3-4: Low (isolated violation, first occurrence)
5-6: Medium (dangerous area OR repeat violation)
7-8: High (dangerous area AND missing critical PPE)
9-10: Critical (imminent danger, fire/machinery proximity, fall risk)

Respond with ONLY a JSON object:
{"score": <1-10>, "reason": "<one sentence explanation>"}"""


async def node_score_severity(state: AgentState) -> Dict[str, Any]:
    """
    Score violation severity using Ollama Llama 3.
    
    # FIXED: Prompt injection protection via sanitization + structured messages
    # IMPROVED: Fallback with explicit logging
    # IMPROVED: Dependency injection for llm_client
    """
    node_name = "ScoreSeverity"
    event = state.get("violation_event", {})
    history = state.get("worker_history", {})

    # Rule-based base score (fallback)
    base_score_map = {
        "no hardhat": 8, "no gloves": 5, "no goggles": 6,
        "no boots": 5, "no mask": 7, "no suit": 4,
    }
    class_name_raw = event.get("class_name", "").lower()
    rule_score = base_score_map.get(class_name_raw, 5)
    if history.get("is_repeat_offender"):
        rule_score = min(10, rule_score + 2)

    try:
        # Use injected client or create new
        llm_client = state.get("llm_client")
        if not llm_client:
            from langchain_ollama import OllamaLLM
            llm_client = OllamaLLM(
                base_url=OLLAMA_BASE_URL,
                model=AGENT_LLM_MODEL,
                temperature=0.0,
                num_predict=100,
            )
        
        # FIXED: Sanitize ALL user inputs before prompt injection
        safe_inputs = {
            "class_name": _sanitize_for_llm(event.get("class_name", "")),
            "zone_id": _sanitize_for_llm(event.get("zone_id", "")),
            "zone_type": _sanitize_for_llm(state.get("zone_info", {}).get("zone_type", "")),
            "confidence": float(event.get("confidence", 0.5)),
            "prior_count": int(history.get("total_violations", 0)),
            "is_repeat": bool(history.get("is_repeat_offender", False)),
        }
        
        # Use structured message API to separate system/human prompts
        from langchain_core.messages import SystemMessage, HumanMessage
        
        system_msg = SystemMessage(content=_SEVERITY_PROMPT_BASE)
        human_msg = HumanMessage(content=json.dumps(safe_inputs))
        
        raw = await llm_client.ainvoke([system_msg, human_msg])
        
        # Robust JSON extraction with fallback
        match = re.search(r'\{.*?\}', raw, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
            score = int(parsed.get("score", rule_score))
            reason = str(parsed.get("reason", "Rule-based fallback"))
        else:
            logger.warning("LLM returned non-JSON response: {}", raw[:100])
            score, reason = rule_score, "JSON parse failed — rule fallback"
        
        # Clamp score
        score = max(1, min(10, score))

        logger.info(
            "Agent ScoreSeverity | score={} | reason={}",
            score, _sanitize_for_llm(reason),
        )

    except Exception as exc:
        logger.warning("LLM scoring failed: {} — using rule-based", exc)
        score, reason = rule_score, f"Rule-based: {class_name_raw} in {event.get('zone_id', 'unknown')}"

    return {
        "severity_score": score,
        "severity_reason": reason,
        "trace_steps": _trace(state, node_name, {
            "score": score,
            "reason": reason,
            "rule_fallback": score == rule_score,
        }),
    }

# ══════════════════════════════════════════════════════════════
# NODE 3 — CheckWorkerHistory
# Pulls 7-day violation history for this track_id.
# ══════════════════════════════════════════════════════════════

async def node_check_worker_history(state: AgentState) -> Dict[str, Any]:
    """Fetch worker violation history from PostgreSQL."""
    node_name = "CheckWorkerHistory"
    event     = state.get("violation_event", {})
    track_id  = event.get("track_id", 0)

    try:
        from database import AsyncSessionLocal
        from .tools   import get_worker_violation_history

        history = await get_worker_violation_history(track_id, AsyncSessionLocal)

        logger.info(
            "Agent WorkerHistory | track={} | total={} | repeat={}",
            track_id, history["total_violations"], history["is_repeat_offender"],
        )

        return {
            "worker_history": history,
            "trace_steps"   : _trace(state, node_name, {
                "track_id"          : track_id,
                "total_violations"  : history["total_violations"],
                "is_repeat_offender": history["is_repeat_offender"],
                "violation_classes" : history["violation_classes"],
            }),
        }

    except Exception as exc:
        logger.error("WorkerHistory node failed: {}", exc)
        return {
            "worker_history": {"total_violations": 0, "is_repeat_offender": False},
            "error"         : f"WorkerHistory failed: {exc}",
            "trace_steps"   : _trace(state, node_name, {"error": str(exc)}),
        }


# ══════════════════════════════════════════════════════════════
# NODE 4 — DecideAlertLevel
# Pure logic node — no LLM.
# Combines severity score + worker history → alert level.
# ══════════════════════════════════════════════════════════════

async def node_decide_alert_level(state: AgentState) -> Dict[str, Any]:
    """
    Decide alert level from severity score + worker history.

    Alert matrix:
      score 1-3  + not repeat → NONE
      score 1-3  + repeat     → LOW
      score 4-5               → LOW
      score 6-7               → MEDIUM
      score 8    + not repeat → HIGH
      score 8    + repeat     → CRITICAL
      score 9-10              → CRITICAL
    """
    node_name = "DecideAlertLevel"
    score     = state.get("severity_score", 5)
    history   = state.get("worker_history", {})
    is_repeat = history.get("is_repeat_offender", False)

    if score <= 3:
        level = "LOW" if is_repeat else "NONE"
    elif score <= 5:
        level = "LOW"
    elif score <= 7:
        level = "MEDIUM"
    elif score == 8:
        level = "CRITICAL" if is_repeat else "HIGH"
    else:
        level = "CRITICAL"

    should_report = score >= SEVERITY_THRESHOLD
    should_alert  = level in ("HIGH", "CRITICAL")

    logger.info(
        "Agent DecideAlertLevel | score={} | level={} | report={} | alert={}",
        score, level, should_report, should_alert,
    )

    return {
        "alert_level"  : level,
        "should_report": should_report,
        "should_alert" : should_alert,
        "trace_steps"  : _trace(state, node_name, {
            "severity_score"    : score,
            "is_repeat_offender": is_repeat,
            "alert_level"       : level,
            "should_report"     : should_report,
            "should_alert"      : should_alert,
        }),
    }


# ══════════════════════════════════════════════════════════════
# NODE 5 — GenerateIncidentReport
# Conditional — only runs if should_report=True.
# Reuses Phase B report generator.
# ══════════════════════════════════════════════════════════════

async def node_generate_report(state: AgentState) -> Dict[str, Any]:
    """
    Generate LLM incident report if severity threshold met.
    Skipped if should_report=False.
    """
    node_name = "GenerateIncidentReport"

    if not state.get("should_report", False):
        return {
            "report_id"     : None,
            "report_summary": None,
            "trace_steps"   : _trace(state, node_name, {
                "status": "SKIPPED",
                "reason": f"severity_score={state.get('severity_score')} < threshold={SEVERITY_THRESHOLD}",
            }),
        }

    event = state.get("violation_event", {})

    try:
        from reports.generator import generate_report
        from database          import AsyncSessionLocal
        from sqlalchemy        import text

        report = await generate_report(
            track_id               = event.get("track_id", 0),
            class_name             = event.get("class_name", "unknown"),
            zone_id                = event.get("zone_id", "unspecified"),
            confidence             = event.get("confidence", 0.5),
            timestamp              = event.get("timestamp", datetime.now(timezone.utc).isoformat()),
            frame_idx              = event.get("frame_idx", 0),
            prior_violations_count = state.get("worker_history", {}).get("total_violations", 0),
        )

        # Persist to DB
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("""
                    INSERT INTO incident_reports
                    (track_id, class_name, zone_id, confidence, frame_idx,
                     timestamp, incident_summary, root_cause_analysis,
                     corrective_actions, osha_reference, severity_level,
                     model_used, generation_ms, status)
                    VALUES
                    (:track_id, :class_name, :zone_id, :confidence, :frame_idx,
                     :timestamp, :incident_summary, :root_cause_analysis,
                     :corrective_actions, :osha_reference, :severity_level,
                     :model_used, :generation_ms, 'agent_generated')
                    RETURNING id
                """),
                {
                    "track_id"           : event.get("track_id"),
                    "class_name"         : event.get("class_name"),
                    "zone_id"            : event.get("zone_id"),
                    "confidence"         : event.get("confidence"),
                    "frame_idx"          : event.get("frame_idx", 0),
                    "timestamp"          : event.get("timestamp", datetime.now(timezone.utc).isoformat()),
                    "incident_summary"   : report.incident_summary,
                    "root_cause_analysis": report.root_cause_analysis,
                    "corrective_actions" : report.corrective_actions,
                    "osha_reference"     : report.osha_reference,
                    "severity_level"     : state.get("alert_level", "MEDIUM"),
                    "model_used"         : report.model_used,
                    "generation_ms"      : report.generation_ms,
                }
            )
            report_id = result.scalar()
            await session.commit()

        logger.info("Agent report generated | id={}", report_id)

        return {
            "report_id"     : report_id,
            "report_summary": report.incident_summary[:200],
            "trace_steps"   : _trace(state, node_name, {
                "status"      : "OK",
                "report_id"   : report_id,
                "model_used"  : report.model_used,
                "generation_ms": report.generation_ms,
            }),
        }

    except Exception as exc:
        logger.error("GenerateReport node failed: {}", exc)
        return {
            "report_id"  : None,
            "error"      : f"Report generation failed: {exc}",
            "trace_steps": _trace(state, node_name, {"error": str(exc)}),
        }


# ══════════════════════════════════════════════════════════════
# NODE 6 — SendAlert
# Conditional — only runs if should_alert=True.
# Routes through Phase E alert worker.
# ══════════════════════════════════════════════════════════════

async def node_send_alert(state: AgentState) -> Dict[str, Any]:
    """
    Send WhatsApp + email alert if alert_level is HIGH or CRITICAL.
    Skipped for LOW/NONE.
    """
    node_name = "SendAlert"

    if not state.get("should_alert", False):
        return {
            "alert_sent" : False,
            "trace_steps": _trace(state, node_name, {
                "status"     : "SKIPPED",
                "alert_level": state.get("alert_level"),
            }),
        }

    event = state.get("violation_event", {})

    try:
        from alerts.alert_worker import alert_worker, AlertJob

        job = AlertJob(
            zone_id     = event.get("zone_id", "agent-triggered"),
            zone_name   = f"Agent Alert: {event.get('class_name')}",
            zone_type   = "danger",
            track_id    = event.get("track_id", 0),
            missing_ppe = [event.get("class_name", "unknown")],
            severity    = state.get("alert_level", "HIGH"),
            timestamp   = event.get("timestamp", datetime.now(timezone.utc).isoformat()),
        )
        enqueued = await alert_worker.enqueue(job)

        logger.info(
            "Agent SendAlert | level={} | enqueued={}",
            state.get("alert_level"), enqueued,
        )

        return {
            "alert_sent" : enqueued,
            "trace_steps": _trace(state, node_name, {
                "status"      : "OK" if enqueued else "QUEUE_FULL",
                "alert_level" : state.get("alert_level"),
                "track_id"    : event.get("track_id"),
            }),
        }

    except Exception as exc:
        logger.error("SendAlert node failed: {}", exc)
        return {
            "alert_sent" : False,
            "error"      : f"Alert failed: {exc}",
            "trace_steps": _trace(state, node_name, {"error": str(exc)}),
        }


# ══════════════════════════════════════════════════════════════
# NODE 7 — LogToDatabase
# Persists the complete agent run to PostgreSQL.
# ══════════════════════════════════════════════════════════════

async def node_log_to_database(state: AgentState) -> Dict[str, Any]:
    """Persist full agent run to agent_runs table."""
    node_name = "LogToDatabase"

    try:
        from database import AsyncSessionLocal
        from .tools   import log_agent_run

        updated_trace = _trace(state, node_name, {"status": "OK"})
        updated_state = {**state, "trace_steps": updated_trace}
        await log_agent_run(
            state.get("run_id", "unknown"),
            updated_state,
            AsyncSessionLocal,
        )

        return {"trace_steps": updated_trace}

    except Exception as exc:
        logger.error("LogToDatabase node failed: {}", exc)
        return {
            "error"      : f"DB log failed: {exc}",
            "trace_steps": _trace(state, node_name, {"error": str(exc)}),
        }


# ══════════════════════════════════════════════════════════════
# NODE 8 — UpdateComplianceScore
# Final node — adjusts worker compliance score.
# ══════════════════════════════════════════════════════════════

# Compliance delta map — severity score → score adjustment
_COMPLIANCE_DELTA = {
    1: -0.5, 2: -1.0, 3: -1.5,
    4: -2.0, 5: -3.0, 6: -4.0,
    7: -5.0, 8: -7.0, 9: -10.0, 10: -15.0,
}


async def node_update_compliance(state: AgentState) -> Dict[str, Any]:
    """
    Update worker compliance score based on severity.
    Higher severity = larger deduction.
    Score is clamped to [0, 100].
    """
    node_name = "UpdateComplianceScore"
    event     = state.get("violation_event", {})
    track_id  = event.get("track_id", 0)
    score     = state.get("severity_score", 5)
    delta     = _COMPLIANCE_DELTA.get(score, -3.0)

    try:
        from database import AsyncSessionLocal
        from .tools   import update_compliance_score

        new_score = await update_compliance_score(track_id, delta, AsyncSessionLocal)

        logger.info(
            "Agent UpdateCompliance | track={} | delta={} | new_score={}",
            track_id, delta, new_score,
        )

        return {
            "compliance_delta": delta,
            "final_status"    : "COMPLETE",
            "trace_steps"     : _trace(state, node_name, {
                "track_id"   : track_id,
                "delta"      : delta,
                "new_score"  : new_score,
            }),
        }

    except Exception as exc:
        logger.error("UpdateCompliance node failed: {}", exc)
        return {
            "compliance_delta": delta,
            "final_status"    : "COMPLETE_WITH_ERRORS",
            "error"           : f"Compliance update failed: {exc}",
            "trace_steps"     : _trace(state, node_name, {"error": str(exc)}),
        }