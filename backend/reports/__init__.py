"""
backend/reports/__init__.py

Public API for report generation utilities.

# Usage:
    from backend.reports import (
        generate_report, GeneratedReport,
        build_pdf, build_weekly_pdf,
        report_debouncer, ReportDebouncer,
        aggregate_weekly_data, generate_and_send,
        get_reports_config, validate_reports_config,
    )
    from backend.reports import ReportsError, ReportGenerationError  # Exceptions

# Example:
    report = await generate_report(track_id=42, class_name='no hardhat', ...)
    pdf_path = build_pdf(report_id=1, report=report, ...)
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .generator import GeneratedReport, generate_report
    from .pdf_builder import build_pdf
    from .trigger import ReportDebouncer, report_debouncer
    from .weekly_report import aggregate_weekly_data, generate_llm_summary
    from .weekly_pdf_builder import build_weekly_pdf
    from .weekly_scheduler import generate_and_send, start_weekly_scheduler

# ── Explicit public API ──────────────────────────────────────
__all__ = [
    # Core functions
    "generate_report",
    "build_pdf",
    "build_weekly_pdf",
    "aggregate_weekly_data",
    "generate_llm_summary",
    "generate_and_send",
    "start_weekly_scheduler",
    
    # Classes
    "GeneratedReport",
    "ReportDebouncer",
    
    # Singletons
    "report_debouncer",
    
    # Exceptions
    "ReportsError",
    "ReportGenerationError",
    "PDFBuildError",
    "DebouncerError",
    
    # Config helpers
    "get_reports_config",
    "validate_reports_config",
]

__version__ = "1.0.0"
__author__ = "Chandrukumar S"
__description__ = "Report generation utilities for Industrial Safety Monitor"


# ── Config helpers ───────────────────────────────────────────
def get_reports_config() -> dict:
    """Return current reports configuration."""
    from .generator import OLLAMA_BASE_URL, OLLAMA_MODEL, REPORT_LLM_PRIMARY
    from .pdf_builder import OUTPUT_DIR as PDF_OUTPUT_DIR
    from .trigger import DEBOUNCE_MINUTES, MAX_QUEUE_SIZE
    from .weekly_scheduler import SEND_DAY, SEND_HOUR
    
    return {
        "llm": {
            "primary": REPORT_LLM_PRIMARY,
            "ollama_url": OLLAMA_BASE_URL,
            "ollama_model": OLLAMA_MODEL,
        },
        "pdf": {
            "output_dir": str(PDF_OUTPUT_DIR),
        },
        "debouncer": {
            "debounce_minutes": DEBOUNCE_MINUTES,
            "max_queue_size": MAX_QUEUE_SIZE,
        },
        "scheduler": {
            "send_day": SEND_DAY,
            "send_hour": SEND_HOUR,
        },
    }


def validate_reports_config() -> list[str]:
    """
    Validate reports config at startup.
    Returns list of warnings (empty = OK).
    """
    warnings = []
    
    # LLM config
    primary = os.getenv("REPORT_LLM_PRIMARY", "ollama")
    if primary not in ("ollama", "openai"):
        warnings.append(f"REPORT_LLM_PRIMARY invalid: {primary} — using 'ollama'")
    
    # Ollama URL
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    if not ollama_url.startswith(("http://", "https://")):
        warnings.append(f"OLLAMA_BASE_URL may be invalid: {ollama_url}")
    
    # PDF output dir
    pdf_dir = os.getenv("REPORT_OUTPUT_DIR", "./reports/output")
    if not os.path.isabs(pdf_dir):
        pdf_dir = os.path.abspath(pdf_dir)
    allowed_dirs = [os.path.abspath(d.strip()) for d in os.getenv("ALLOWED_REPORT_DIRS", "./reports").split(",") if d.strip()]
    if not any(pdf_dir.startswith(d) for d in allowed_dirs):
        warnings.append(f"REPORT_OUTPUT_DIR not in allowed directories: {pdf_dir}")
    
    # Debouncer config
    try:
        debounce = int(os.getenv("REPORT_DEBOUNCE_MINUTES", "480"))
        if not 60 <= debounce <= 1440:
            warnings.append(f"REPORT_DEBOUNCE_MINUTES={debounce} outside 60-1440 range")
    except ValueError:
        warnings.append("REPORT_DEBOUNCE_MINUTES must be an integer")
    
    try:
        queue_size = int(os.getenv("REPORT_MAX_QUEUE_SIZE", "50"))
        if not 10 <= queue_size <= 500:
            warnings.append(f"REPORT_MAX_QUEUE_SIZE={queue_size} outside 10-500 range")
    except ValueError:
        warnings.append("REPORT_MAX_QUEUE_SIZE must be an integer")
    
    # Scheduler config
    try:
        send_hour = int(os.getenv("WEEKLY_REPORT_SEND_HOUR", "8"))
        if not 0 <= send_hour <= 23:
            warnings.append(f"WEEKLY_REPORT_SEND_HOUR={send_hour} outside 0-23 range")
    except ValueError:
        warnings.append("WEEKLY_REPORT_SEND_HOUR must be an integer")
    
    send_day = os.getenv("WEEKLY_REPORT_SEND_DAY", "Monday")
    valid_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    if send_day not in valid_days:
        warnings.append(f"WEEKLY_REPORT_SEND_DAY invalid: {send_day} — using 'Monday'")
    
    return warnings


# ── Lazy loader for heavy imports ────────────────────────────
def __getattr__(name: str) -> Any:
    """Lazy-load submodules only when accessed."""
    
    if name in ("GeneratedReport", "generate_report"):
        from . import generator as module
        return getattr(module, name)
    
    if name in ("build_pdf",):
        from . import pdf_builder as module
        return getattr(module, name)
    
    if name in ("ReportDebouncer", "report_debouncer"):
        from . import trigger as module
        return getattr(module, name)
    
    if name in ("aggregate_weekly_data", "generate_llm_summary"):
        from . import weekly_report as module
        return getattr(module, name)
    
    if name in ("build_weekly_pdf",):
        from . import weekly_pdf_builder as module
        return getattr(module, name)
    
    if name in ("generate_and_send", "start_weekly_scheduler"):
        from . import weekly_scheduler as module
        return getattr(module, name)
    
    if name in ("ReportsError", "ReportGenerationError", "PDFBuildError", "DebouncerError"):
        from . import generator as module
        return getattr(module, name)
    
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


# ── Run validation at import (non-blocking warnings) ─────────
_reports_warnings = validate_reports_config()
if _reports_warnings and os.getenv("REPORTS_STRICT_MODE", "false").lower() == "true":
    import warnings as _warnings
    for w in _reports_warnings:
        _warnings.warn(f"Reports config: {w}", RuntimeWarning, stacklevel=2)