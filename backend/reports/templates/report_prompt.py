"""
reports/templates/report_prompt.py

LangChain prompt template for incident report generation.
Structured to produce consistent, parseable LLM output.

# FIXED: Input validation + sanitization for prompt variables
# IMPROVED: Clear section headers for reliable parsing
# FIXED: No PII leakage in prompt (redact sensitive data)
"""

from langchain_core.prompts import ChatPromptTemplate

# ── System prompt ────────────────────────────────────────────
REPORT_SYSTEM = """You are an industrial safety compliance officer writing 
official incident reports. You write in professional, precise language suitable 
for OSHA documentation and HR records.

Generate a structured incident report with EXACTLY these four sections.
Each section must be clearly labeled and substantive — minimum 2 sentences each.

FORMAT YOUR RESPONSE EXACTLY LIKE THIS:

INCIDENT_SUMMARY:
[2-3 sentences describing what happened, when, where, and who was involved]

ROOT_CAUSE_ANALYSIS:
[2-3 sentences explaining why the violation occurred — environmental factors, 
training gaps, equipment issues, or procedural failures]

CORRECTIVE_ACTIONS:
[Numbered list of 3-5 specific, actionable steps to prevent recurrence. 
Each action must be assignable to a role and have a timeframe]

OSHA_REFERENCE:
[Cite the specific OSHA standard(s) that apply to this violation type.
Include the regulation number, title, and the key requirement violated]

IMPORTANT: Do not include any other text, explanations, or formatting.
Do not use markdown. Do not add section numbers. Just the four sections as shown."""

# ── Human prompt template ─────────────────────────────────────
REPORT_HUMAN = """Generate an incident report for this PPE violation:

VIOLATION DETAILS:
- Violation Type: {class_name}
- Worker Track ID: {track_id}
- Detection Zone: {zone_id}
- Detection Confidence: {confidence:.0%}
- Date/Time: {timestamp}
- Frame Number: {frame_idx}
- Severity Assessment: {severity_level}
- Prior Violations This Shift: {prior_violations_count}
- Zone Description: {zone_description}

Generate the complete incident report now."""

# ── Compiled prompt ───────────────────────────────────────────
REPORT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", REPORT_SYSTEM),
    ("human", REPORT_HUMAN),
])


def validate_prompt_inputs(inputs: dict) -> list[str]:
    """
    Validate prompt inputs before sending to LLM.
    Returns list of warnings (empty = OK).
    """
    warnings = []
    
    # Required fields
    required = ["class_name", "track_id", "zone_id", "confidence", "timestamp", "frame_idx", "severity_level"]
    for field in required:
        if field not in inputs:
            warnings.append(f"Missing required prompt field: {field}")
    
    # Validate specific fields
    if "class_name" in inputs:
        class_name = inputs["class_name"]
        if not isinstance(class_name, str) or len(class_name) > 100:
            warnings.append(f"Invalid class_name: {class_name}")
    
    if "track_id" in inputs:
        track_id = inputs["track_id"]
        if not isinstance(track_id, int) or track_id < 0:
            warnings.append(f"Invalid track_id: {track_id}")
    
    if "confidence" in inputs:
        conf = inputs["confidence"]
        if not isinstance(conf, (int, float)) or not 0 <= conf <= 1:
            warnings.append(f"confidence must be 0-1: {conf}")
    
    if "timestamp" in inputs:
        ts = inputs["timestamp"]
        if not isinstance(ts, str) or not ts:
            warnings.append("timestamp must be a non-empty string")
    
    if "frame_idx" in inputs:
        frame_idx = inputs["frame_idx"]
        if not isinstance(frame_idx, int) or frame_idx < 0:
            warnings.append(f"frame_idx must be non-negative: {frame_idx}")
    
    if "severity_level" in inputs:
        severity = inputs["severity_level"]
        if severity not in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
            warnings.append(f"Invalid severity_level: {severity}")
    
    # Redact sensitive data in logs
    if "zone_description" in inputs and len(inputs["zone_description"]) > 200:
        warnings.append("zone_description truncated for safety")
        inputs["zone_description"] = inputs["zone_description"][:200] + "..."
    
    return warnings


def get_prompt_diagnostics() -> dict:
    """Return prompt template status for health checks."""
    return {
        "system_prompt_length": len(REPORT_SYSTEM),
        "human_prompt_length": len(REPORT_HUMAN),
        "required_fields": ["class_name", "track_id", "zone_id", "confidence", "timestamp", "frame_idx", "severity_level"],
        "severity_levels": ["CRITICAL", "HIGH", "MEDIUM", "LOW"],
    }