"""
backend/event_writer.py

Background coroutine that drains the inference queue,
updates the latest_frame state, persists violation events
to SQLite, and triggers zone risk snapshots.

# FIXED: Proper async error handling with rollback
# FIXED: Input validation for violation data
# IMPROVED: Configurable zone risk snapshot interval
# IMPROVED: Dependency injection for testability
# FIXED: No PII leakage in logs
# IMPROVED: Memory-efficient batch processing
"""

from __future__ import annotations

import asyncio
from typing import List, Optional, TYPE_CHECKING

from loguru import logger

# Avoid circular imports
if TYPE_CHECKING:
    from .inference.pipeline import InferencePipeline, FrameResult
    from .state import AppState
    from .database import AsyncSessionLocal

# ── Config: Load from env with validation ─────────────────────
ZONE_RISK_SNAPSHOT_INTERVAL: int = int(
    __import__('os').getenv("ZONE_RISK_SNAPSHOT_INTERVAL", "30")
)
if ZONE_RISK_SNAPSHOT_INTERVAL < 10 or ZONE_RISK_SNAPSHOT_INTERVAL > 300:
    logger.warning("ZONE_RISK_SNAPSHOT_INTERVAL invalid — using 30")
    ZONE_RISK_SNAPSHOT_INTERVAL = 30

MAX_BATCH_SIZE: int = int(
    __import__('os').getenv("EVENT_WRITER_MAX_BATCH_SIZE", "100")
)
if MAX_BATCH_SIZE < 10 or MAX_BATCH_SIZE > 1000:
    logger.warning("EVENT_WRITER_MAX_BATCH_SIZE invalid — using 100")
    MAX_BATCH_SIZE = 100


# ── Helpers (each independently testable) ────────────────────

async def _persist_violations(
    violations: List['TrackedDetection'],  # type: ignore
    session_factory,  # AsyncSessionLocal
) -> None:
    """
    Write a batch of violation detections to the DB in one session.
    
    # FIXED: Input validation for bbox coordinates
    # FIXED: Proper error handling with rollback
    # IMPROVED: Batch size limiting for memory efficiency
    """
    if not violations:
        return
    
    # Limit batch size to prevent memory issues
    batch = violations[:MAX_BATCH_SIZE]
    
    from .models import ViolationEvent
    
    async with session_factory() as session:
        try:
            for viol in batch:
                # Validate bbox coordinates
                bbox = viol.bbox_xyxy
                if len(bbox) != 4:
                    logger.warning(
                        "Skipping violation with unexpected bbox length {}: {}",
                        len(bbox), bbox,
                    )
                    continue
                
                x1, y1, x2, y2 = bbox
                
                # Validate coordinate order
                if x1 >= x2 or y1 >= y2:
                    logger.warning(
                        "Skipping violation with invalid bbox order: {}", bbox,
                    )
                    continue
                
                # Validate confidence
                if not 0 <= viol.confidence <= 1:
                    logger.warning(
                        "Skipping violation with invalid confidence: {}",
                        viol.confidence,
                    )
                    continue
                
                event = ViolationEvent(
                    track_id=viol.track_id,
                    class_name=viol.class_name,
                    confidence=round(viol.confidence, 3),
                    zone_id=viol.zone_id,
                    bbox_x1=round(x1, 1),
                    bbox_y1=round(y1, 1),
                    bbox_x2=round(x2, 1),
                    bbox_y2=round(y2, 1),
                    frame_idx=viol.frame_idx,
                )
                session.add(event)
            
            await session.commit()
            logger.debug("Persisted {} violations", len(batch))
            
        except Exception as exc:
            logger.error("Violation DB write failed: {}", exc)
            await session.rollback()
            raise


async def _persist_zone_risks(
    zone_risks: List[dict],
    session_factory,  # AsyncSessionLocal
) -> None:
    """Write a zone risk snapshot batch in one session."""
    if not zone_risks:
        return
    
    from .models import ZoneRiskRecord
    
    async with session_factory() as session:
        try:
            for zr in zone_risks:
                # Validate required fields with .get() to avoid KeyError
                zone_id = zr.get("zone_id")
                if not zone_id:
                    logger.warning(
                        "Skipping zone risk entry missing 'zone_id': {}", zr
                    )
                    continue
                
                # Validate numeric fields
                mean_intensity = zr.get("mean_intensity", 0.0)
                max_intensity = zr.get("max_intensity", 0.0)
                violation_pct = zr.get("violation_pct", 0.0)
                
                if not 0 <= mean_intensity <= 1 or not 0 <= max_intensity <= 1 or not 0 <= violation_pct <= 1:
                    logger.warning(
                        "Skipping zone risk with invalid intensity/pct values: {}", zr
                    )
                    continue
                
                record = ZoneRiskRecord(
                    zone_id=zone_id,
                    mean_intensity=round(mean_intensity, 4),
                    max_intensity=round(max_intensity, 4),
                    violation_pct=round(violation_pct, 4),
                    risk_level=zr.get("risk_level", "low"),
                )
                session.add(record)
            
            await session.commit()
            logger.debug("Persisted {} zone risk records", len(zone_risks))
            
        except Exception as exc:
            logger.error("Zone risk DB write failed: {}", exc)
            await session.rollback()
            raise


# ── Main loop ─────────────────────────────────────────────────

async def start_event_writer(
    pipeline: 'InferencePipeline',  # type: ignore
    app_state: 'AppState',  # type: ignore
    session_factory=None,  # AsyncSessionLocal, injected for testing
) -> None:
    """
    Drains pipeline.results() and:
      1. Updates app_state.latest_frame (read by /stream and /live)
      2. Persists violations to SQLite
      3. Writes zone risk snapshots every ZONE_RISK_SNAPSHOT_INTERVAL frames
      
    # IMPROVED: Dependency injection for session_factory (testing)
    # FIXED: Proper error handling with graceful shutdown
    # IMPROVED: Memory-efficient processing with batch limits
    """
    if session_factory is None:
        from .database import AsyncSessionLocal
        session_factory = AsyncSessionLocal
    
    logger.info("Event writer started | snapshot_interval={}", ZONE_RISK_SNAPSHOT_INTERVAL)
    frame_count = 0
    violation_count = 0

    try:
        async for frame_result in pipeline.results():
            # Thread-safe state update shared with FastAPI routes.
            # This is a plain setter because the pipeline now runs in its own
            # worker thread, not on the FastAPI request loop.
            app_state.set_latest_frame(frame_result)
            frame_count += 1

            # Persist violations if any
            if frame_result.violations:
                await _persist_violations(frame_result.violations, session_factory)
                violation_count += len(frame_result.violations)

            # Write zone risk snapshots at interval
            if (frame_count % ZONE_RISK_SNAPSHOT_INTERVAL == 0 
                and frame_result.zone_risks):
                await _persist_zone_risks(frame_result.zone_risks, session_factory)

            # Yield control to event loop (prevent starvation)
            await asyncio.sleep(0)

    except asyncio.CancelledError:
        logger.info(
            "Event writer cancelled after {} frames, {} violations — shutting down cleanly",
            frame_count, violation_count,
        )
        raise
    except Exception as exc:
        logger.exception(
            "Event writer terminated unexpectedly after {} frames, {} violations: {}",
            frame_count, violation_count, type(exc).__name__,
        )
        raise
    finally:
        logger.info(
            "Event writer stopped cleanly | frames={} | violations={}",
            frame_count, violation_count,
        )
