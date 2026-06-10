"""
mlops/deployment_manager.py

Orchestrates model deployments — canary start, evaluation,
promotion, and rollback.

# FIXED: Input validation + sanitization for all public methods
# FIXED: Config validation at module load
# IMPROVED: Parameterized queries only — no SQL injection
# IMPROVED: Dependency injection for testability
# FIXED: No credential leakage in logs (Slack webhook redaction)
# IMPROVED: Async-safe state management + error recovery

Called from:
  - API endpoints (manual trigger)
  - Automatic evaluation loop (after retraining)
  - Slack webhook (for human-in-the-loop approval)
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Protocol, runtime_checkable

from loguru import logger
from pydantic import BaseModel, Field, field_validator  # FIXED: Pydantic v2 compatibility

# ── Config: Load from env with validation ─────────────────────
def _validate_float_range(name: str, value: str, default: float, min_val: float, max_val: float) -> float:
    try:
        val = float(value)
        if not min_val <= val <= max_val:
            raise ValueError(f"{name} must be {min_val}-{max_val}, got {val}")
        return val
    except ValueError:
        logger.warning("{} invalid: {} — using default {}", name, value, default)
        return default

AUTO_PROMOTE = os.getenv("AUTO_PROMOTE_CANARY", "false").lower() == "true"
EVAL_INTERVAL_S = _validate_float_range("MLOPS_EVAL_INTERVAL_S", os.getenv("MLOPS_EVAL_INTERVAL_S", "60.0"), 60.0, 10.0, 3600.0)

# Slack config
SLACK_DEPLOY_WEBHOOK = os.getenv("SLACK_DEPLOY_WEBHOOK", "")
if SLACK_DEPLOY_WEBHOOK and not SLACK_DEPLOY_WEBHOOK.startswith("https://hooks.slack.com/"):
    logger.warning("SLACK_DEPLOY_WEBHOOK may be invalid — notifications may fail")

# ── Protocol for dependency injection ─────────────────────────
@runtime_checkable
class DBFactoryProtocol(Protocol):
    """Protocol for async session factory — enables mocking in tests."""
    def __call__(self): ...

@runtime_checkable
class CanaryRouterProtocol(Protocol):
    """Protocol for canary router — enables mocking in tests."""
    def start_canary(self, canary_version: str, production_version: str, deployment_id: int, canary_pct: Optional[float] = None) -> None: ...
    def stop_canary(self) -> None: ...
    def get_status(self) -> Dict[str, Any]: ...

# ── Pydantic models for structured validation ─────────────────
class DeploymentConfig(BaseModel):
    """Validated configuration for deployment operations."""
    auto_promote: bool = Field(default=AUTO_PROMOTE)
    eval_interval_s: float = Field(default=EVAL_INTERVAL_S, ge=10, le=3600)
    slack_webhook: Optional[str] = Field(default=None)
    # FIXED: canary_pct was missing — hasattr() checks always returned False downstream
    canary_pct: float = Field(default=10.0, ge=0.0, le=100.0)
    
    @field_validator("slack_webhook")
    @classmethod
    def validate_webhook_format(cls, v):
        if v and not v.startswith("https://hooks.slack.com/"):
            logger.warning("Slack webhook format may be invalid")
        return v

# ── Custom exceptions ────────────────────────────────────────
class MLOpsError(Exception):
    """Base exception for MLOps operations."""
    pass

class DeploymentError(MLOpsError):
    """Raised when deployment operation fails."""
    pass

# ── Helper: Redact sensitive data for logging ────────────────
def _redact_webhook(webhook: str) -> str:
    """Redact Slack webhook URL for safe logging."""
    if not webhook:
        return "***"
    # Show only domain, hide token
    match = re.match(r'https://hooks\.slack\.com/services/[^/]+/[^/]+/([^/]+)', webhook)
    if match:
        token = match.group(1)
        return f"https://hooks.slack.com/services/***/***/{token[-4:]}"
    return "***"

# ── Core deployment operations ───────────────────────────────

async def start_canary_deployment(
    canary_version: str,
    db_factory: DBFactoryProtocol,
    notes: str = "",
    config: Optional[DeploymentConfig] = None,
    router: Optional[CanaryRouterProtocol] = None,
) -> Optional[int]:
    """
    Begin canary deployment for a staging model version.
    
    # FIXED: Parameterized queries only — no SQL injection
    # FIXED: Input validation + sanitization
    # IMPROVED: Dependency injection for testability
    
    Args:
        canary_version: MLflow model version to canary.
        db_factory: AsyncSessionLocal factory.
        notes: Human notes for deployment record.
        config: Optional override config.
        router: Optional injected router for testing.
        
    Returns:
        deployment_id if started, None on failure.
        
    Raises:
        DeploymentError: If deployment fails.
    """
    cfg = config or DeploymentConfig()
    
    # Validate inputs
    if not canary_version or not re.match(r'^[a-zA-Z0-9._-]+$', canary_version):
        raise DeploymentError(f"Invalid canary_version format: {canary_version}")
    if len(notes) > 1000:
        notes = notes[:1000] + "..."  # Truncate long notes
    
    # Import here to avoid circular dependency
    from .model_registry import get_production_model, get_staging_models, MODEL_NAME
    
    prod_model = get_production_model()
    prod_v = prod_model.version if prod_model else "none"
    prod_map = prod_model.map50 if prod_model else 0.0
    
    # Get staging model info
    staging = [m for m in get_staging_models() if m.version == canary_version]
    if not staging:
        logger.error("Canary v{} not found in Staging stage", canary_version)
        return None
    
    staging_model = staging[0]
    
    # Validate staging model metrics
    if staging_model.map50 < 0 or staging_model.map50 > 1:
        raise DeploymentError(f"Invalid mAP for canary v{canary_version}: {staging_model.map50}")
    
    from sqlalchemy import text
    
    async with db_factory() as session:
        try:
            result = await session.execute(
                text("""
                    INSERT INTO model_deployments
                    (model_name, model_version, mlflow_run_id,
                     stage, map50, map50_95, canary_traffic_pct, notes, created_at)
                    VALUES
                    (:name, :version, :run_id,
                     'canary', :map50, :map50_95, :pct, :notes, NOW())
                    RETURNING id
                """),
                {
                    "name": MODEL_NAME,
                    "version": canary_version,
                    "run_id": staging_model.run_id,
                    "map50": staging_model.map50,
                    "map50_95": staging_model.map50_95,
                    "pct": cfg.canary_pct if hasattr(cfg, 'canary_pct') else float(os.getenv("CANARY_TRAFFIC_PCT", "10")),
                    "notes": notes,
                }
            )
            deployment_id = result.scalar()
            await session.commit()
            
        except Exception as exc:
            await session.rollback()
            logger.error("Failed to create deployment record: {}", exc)
            raise DeploymentError(f"DB insert failed: {exc}")
    
    # Activate router (injectable for testing)
    router_to_use = router or __import__('backend.mlops.canary_router', fromlist=['canary_router']).canary_router
    try:
        router_to_use.start_canary(
            canary_version=canary_version,
            production_version=prod_v,
            deployment_id=deployment_id,
        )
    except Exception as exc:
        logger.error("Failed to activate canary router: {}", exc)
        # Rollback DB record
        async with db_factory() as session:
            await session.execute(
                text("DELETE FROM model_deployments WHERE id=:id"),
                {"id": deployment_id}
            )
            await session.commit()
        raise DeploymentError(f"Router activation failed: {exc}")
    
    # Notify Slack (redact webhook in logs)
    await _notify_slack(
        f"🐦 Canary deployment started | "
        f"v{canary_version} (mAP={staging_model.map50:.4f}) → "
        f"10% traffic | prod=v{prod_v} (mAP={prod_map:.4f})",
        webhook=cfg.slack_webhook,
    )
    
    logger.info(
        "Canary deployment started | id={} | v{} vs v{}",
        deployment_id, canary_version, prod_v,
    )
    return deployment_id


async def promote_canary(
    deployment_id: int,
    db_factory: DBFactoryProtocol,
    reason: str = "Canary evaluation passed",
    config: Optional[DeploymentConfig] = None,
    router: Optional[CanaryRouterProtocol] = None,
) -> bool:
    """
    Promote canary model to production.
    Archives current production model.
    
    # FIXED: Parameterized queries only — no SQL injection
    # FIXED: Input validation + sanitization
    # IMPROVED: Dependency injection for testability
    """
    cfg = config or DeploymentConfig()
    
    # Validate inputs
    if not isinstance(deployment_id, int) or deployment_id < 1:
        logger.error("Invalid deployment_id: {}", deployment_id)
        return False
    if len(reason) > 500:
        reason = reason[:500] + "..."
    
    from sqlalchemy import text
    
    # Get canary version from DB
    async with db_factory() as session:
        result = await session.execute(
            text("SELECT model_version FROM model_deployments WHERE id=:id AND stage='canary'"),
            {"id": deployment_id}
        )
        row = result.mappings().first()
    
    if not row:
        logger.error("Canary deployment {} not found or not in 'canary' stage", deployment_id)
        return False
    
    version = row["model_version"]
    
    # Promote in model registry
    from .model_registry import promote_to_production
    success = promote_to_production(version)
    
    if success:
        # Update DB
        async with db_factory() as session:
            try:
                await session.execute(
                    text("""
                        UPDATE model_deployments
                        SET stage='production', promoted_at=NOW(), promotion_reason=:reason
                        WHERE id=:id
                    """),
                    {"id": deployment_id, "reason": reason}
                )
                await session.commit()
            except Exception as exc:
                logger.error("Failed to update deployment record: {}", exc)
                await session.rollback()
                return False
        
        # Stop router (injectable)
        router_to_use = router or __import__('backend.mlops.canary_router', fromlist=['canary_router']).canary_router
        try:
            router_to_use.stop_canary()
        except Exception as exc:
            logger.warning("Failed to stop canary router: {}", exc)
            # Continue — promotion already succeeded
        
        # Notify Slack
        await _notify_slack(
            f"✅ Canary PROMOTED to Production | "
            f"v{version} now serves 100% traffic | {reason}",
            webhook=cfg.slack_webhook,
        )
        logger.info("Canary v{} promoted to production | reason={}", version, reason)
    
    return success


async def rollback_canary(
    deployment_id: int,
    db_factory: DBFactoryProtocol,
    reason: str = "Evaluation failed",
    config: Optional[DeploymentConfig] = None,
    router: Optional[CanaryRouterProtocol] = None,
) -> bool:
    """
    Roll back canary — stop routing, archive canary version.
    Production model continues unaffected.
    
    # FIXED: Parameterized queries only — no SQL injection
    # FIXED: Input validation + sanitization
    # IMPROVED: Dependency injection for testability
    """
    cfg = config or DeploymentConfig()
    
    # Validate inputs
    if not isinstance(deployment_id, int) or deployment_id < 1:
        logger.error("Invalid deployment_id: {}", deployment_id)
        return False
    if len(reason) > 500:
        reason = reason[:500] + "..."
    
    from sqlalchemy import text
    
    # Get canary version from DB
    async with db_factory() as session:
        result = await session.execute(
            text("SELECT model_version FROM model_deployments WHERE id=:id AND stage='canary'"),
            {"id": deployment_id}
        )
        row = result.mappings().first()
    
    if not row:
        logger.warning("Canary deployment {} not found or not in 'canary' stage", deployment_id)
        return False
    
    version = row["model_version"]
    
    # Stop routing immediately (injectable)
    router_to_use = router or __import__('backend.mlops.canary_router', fromlist=['canary_router']).canary_router
    try:
        router_to_use.stop_canary()
    except Exception as exc:
        logger.warning("Failed to stop canary router: {}", exc)
        # Continue — we still want to archive the model
    
    # Archive the failed canary
    from .model_registry import archive_model
    archive_model(version, reason=reason)
    
    # Update DB
    async with db_factory() as session:
        try:
            await session.execute(
                text("""
                    UPDATE model_deployments
                    SET stage='archived',
                        rolled_back_at=NOW(),
                        rollback_reason=:reason
                    WHERE id=:id
                """),
                {"id": deployment_id, "reason": reason}
            )
            await session.commit()
        except Exception as exc:
            logger.error("Failed to update deployment record: {}", exc)
            await session.rollback()
            return False
    
    # Notify Slack
    await _notify_slack(
        f"⚠️ Canary ROLLED BACK | v{version} archived | Reason: {reason}",
        webhook=cfg.slack_webhook,
    )
    logger.warning("Canary v{} rolled back | {}", version, reason)
    return True


async def run_canary_evaluation_loop(
    db_factory: DBFactoryProtocol,
    config: Optional[DeploymentConfig] = None,
    router: Optional[CanaryRouterProtocol] = None,
) -> None:
    """
    Background loop that periodically evaluates active canary deployments.
    Runs in FastAPI lifespan as asyncio task.
    
    # IMPROVED: Async-safe state management + error recovery
    # IMPROVED: Dependency injection for testability
    """
    cfg = config or DeploymentConfig()
    
    logger.info("Canary evaluation loop started | interval={}s", cfg.eval_interval_s)
    
    while True:
        try:
            await asyncio.sleep(cfg.eval_interval_s)
            
            # Get router status (injectable)
            router_to_use = router or __import__('backend.mlops.canary_router', fromlist=['canary_router']).canary_router
            status = router_to_use.get_status()
            
            if not status["active"]:
                continue
            
            dep_id = status["deployment_id"]
            if not dep_id or not status["evaluation_ready"]:
                continue
            
            # Evaluate canary
            from .canary_evaluator import evaluate_canary, EvaluationVerdict
            result = await evaluate_canary(dep_id, db_factory)
            
            logger.info(
                "Canary eval | verdict={} | Δconf={:+.4f} | frames={}",
                result.verdict.value,
                result.confidence_delta,
                result.canary_frames,
            )
            
            # Take action based on verdict
            if result.verdict == EvaluationVerdict.ROLLBACK:
                success = await rollback_canary(
                    dep_id, db_factory, result.reason,
                    config=cfg, router=router_to_use,
                )
                if not success:
                    logger.error("Rollback failed for deployment {}", dep_id)
            
            elif result.verdict == EvaluationVerdict.PROMOTE:
                if cfg.auto_promote:
                    success = await promote_canary(
                        dep_id, db_factory, result.reason,
                        config=cfg, router=router_to_use,
                    )
                    if not success:
                        logger.error("Promotion failed for deployment {}", dep_id)
                else:
                    # Notify for manual approval
                    await _notify_slack(
                        f"✅ Canary ready to promote! "
                        f"Δconf={result.confidence_delta:+.4f} | "
                        f"frames={result.canary_frames} | "
                        f"Manual promotion required via /mlops/promote",
                        webhook=cfg.slack_webhook,
                    )
                    logger.info("Canary ready for manual promotion | deployment={}", dep_id)
            
            elif result.verdict == EvaluationVerdict.EXTEND:
                logger.debug("Canary evaluation: extend | deployment={}", dep_id)
        
        except asyncio.CancelledError:
            logger.info("Canary evaluation loop cancelled")
            break
        except Exception as exc:
            logger.exception("Canary evaluation error: {}", type(exc).__name__)
            # Continue loop — don't crash the entire app
            await asyncio.sleep(10)  # Brief pause before retry


async def _notify_slack(message: str, webhook: Optional[str] = None) -> None:
    """
    Send deployment notification to Slack.
    
    # FIXED: Redact webhook in logs
    # IMPROVED: Async HTTP client + timeout handling
    """
    webhook_to_use = webhook or SLACK_DEPLOY_WEBHOOK
    if not webhook_to_use:
        return
    
    # Redact webhook for logging
    safe_webhook = _redact_webhook(webhook_to_use)
    
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                webhook_to_use,
                json={"text": f"🏗 MLOps: {message}"},
                headers={"Content-Type": "application/json"},
            )
            if response.status_code != 200:
                logger.warning(
                    "Slack notification failed: {} | webhook={}",
                    response.status_code, safe_webhook,
                )
            else:
                logger.debug("Slack notification sent | webhook={}", safe_webhook)
    except ImportError:
        logger.debug("httpx not installed — skipping Slack notification")
    except Exception as exc:
        logger.warning(
            "Slack notification failed: {} | webhook={}",
            type(exc).__name__, safe_webhook,
        )