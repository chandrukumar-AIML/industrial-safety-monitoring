"""
retraining/model_promoter.py

Compares new retrained model mAP against current production model.
Promotes new model if it meets the improvement threshold.
Sends Slack notifications on all outcomes.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import shutil
from loguru import logger

import httpx

SLACK_WEBHOOK         = os.getenv("RETRAIN_NOTIFY_SLACK_WEBHOOK", "")
MIN_MAP_IMPROVEMENT   = float(os.getenv("NEW_MODEL_MIN_MAP_IMPROVEMENT", "0.01"))

# FIXED: Relative paths resolve wrong inside Docker — use env-var-based absolute paths
_MODELS_DIR = pathlib.Path(os.getenv("MODELS_DIR", "models")).resolve()
PRODUCTION_MODEL_PATH = _MODELS_DIR / "best.pt"
STAGING_MODEL_PATH    = _MODELS_DIR / "candidate.pt"
BACKUP_MODEL_PATH     = _MODELS_DIR / "best_backup.pt"


async def notify_slack(message: str) -> None:
    """Send a notification to Slack webhook."""
    if not SLACK_WEBHOOK:
        logger.debug("Slack webhook not configured — skipping notification")
        return
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                SLACK_WEBHOOK,
                json={"text": f"🏗 Safety Monitor MLOps: {message}"},
            )
    except Exception as exc:
        logger.warning("Slack notification failed: {}", exc)


def get_current_map() -> float:
    """
    Read current production model mAP from training_summary.json.
    Returns 0.0 if not found (forces promotion of any valid new model).
    """
    summary_path = _MODELS_DIR / "training_summary.json"
    if not summary_path.exists():
        logger.warning("training_summary.json not found — current mAP assumed 0.0")
        return 0.0

    data = json.loads(summary_path.read_text())
    return float(data.get("map50", 0.0))


def get_candidate_map(candidate_summary_path: str) -> float:
    """Read new candidate model's mAP from its training summary."""
    p = pathlib.Path(candidate_summary_path)
    if not p.exists():
        raise FileNotFoundError(f"Candidate summary not found: {p}")
    data = json.loads(p.read_text())
    return float(data.get("map50", 0.0))


async def evaluate_and_promote(candidate_summary_path: str) -> dict:
    """
    Compare candidate vs production model.
    Promote if improvement >= MIN_MAP_IMPROVEMENT.

    Args:
        candidate_summary_path: Path to new model's training_summary.json

    Returns:
        Promotion result dict.
    """
    current_map   = get_current_map()
    candidate_map = get_candidate_map(candidate_summary_path)
    improvement   = candidate_map - current_map
    promoted      = improvement >= MIN_MAP_IMPROVEMENT

    logger.info(
        "Model comparison | current mAP={:.4f} | candidate mAP={:.4f} "
        "| improvement={:+.4f} | threshold={} | promoted={}",
        current_map, candidate_map, improvement, MIN_MAP_IMPROVEMENT, promoted,
    )

    if promoted:
        # Backup current model
        if PRODUCTION_MODEL_PATH.exists():
            shutil.copy2(PRODUCTION_MODEL_PATH, BACKUP_MODEL_PATH)
            logger.info("Current model backed up → {}", BACKUP_MODEL_PATH)

        # FIXED: Raise clearly if staging model is missing — silent pass hid broken promotions
        if not STAGING_MODEL_PATH.exists():
            raise FileNotFoundError(
                f"Candidate model not found at {STAGING_MODEL_PATH} — promotion aborted"
            )

        # Promote candidate
        _MODELS_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(STAGING_MODEL_PATH, PRODUCTION_MODEL_PATH)
        logger.info("Candidate promoted → {}", PRODUCTION_MODEL_PATH)

        # Update training summary
        candidate_data = json.loads(pathlib.Path(candidate_summary_path).read_text())
        summary_dest = _MODELS_DIR / "training_summary.json"
        summary_dest.write_text(json.dumps(candidate_data, indent=2))

        await notify_slack(
            f"✅ New model PROMOTED! "
            f"mAP: {current_map:.4f} → {candidate_map:.4f} "
            f"(+{improvement:.4f}). "
            f"Production updated. Railway redeploy triggered."
        )
    else:
        await notify_slack(
            f"❌ Candidate model NOT promoted. "
            f"mAP: {candidate_map:.4f} vs current {current_map:.4f} "
            f"(improvement {improvement:+.4f} < threshold {MIN_MAP_IMPROVEMENT}). "
            f"Keeping existing production model."
        )

    return {
        "promoted"      : promoted,
        "current_map"   : current_map,
        "candidate_map" : candidate_map,
        "improvement"   : round(improvement, 4),
        "threshold"     : MIN_MAP_IMPROVEMENT,
    }