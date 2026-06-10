"""
alerts/alert_worker.py

Main alert dispatcher.

# FIXED: Non-blocking image encoding via thread pool
# FIXED: AlertJob validation with Pydantic
# IMPROVED: Configurable thresholds via env vars
# IMPROVED: Dependency injection for testability
# FIXED: Retry logic for transient send failures
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import List, Optional, Protocol, runtime_checkable

import cv2
import numpy as np
from loguru import logger
from pydantic import BaseModel, Field, field_validator, model_validator  # FIXED: Pydantic v2 compatibility

from .throttle import alert_throttle
from .whatsapp_sender import send_whatsapp_alert
from .email_sender import send_email_alert

# ── Config: Load from env with validation ─────────────────────
_RECIPIENT_REFRESH_S = max(10, int(os.getenv("ALERT_RECIPIENT_REFRESH_SECONDS", "60")))
_MAX_QUEUE_SIZE = max(10, int(os.getenv("ALERT_QUEUE_MAX_SIZE", "100")))
_IMAGE_ENCODE_QUALITY = int(os.getenv("ALERT_IMAGE_JPEG_QUALITY", "75"))
_SEND_RETRY_ATTEMPTS = int(os.getenv("ALERT_SEND_RETRY_ATTEMPTS", "3"))

# FIXED: module-level raise → warning + clamp
if _RECIPIENT_REFRESH_S < 10:
    logger.warning("ALERT_RECIPIENT_REFRESH_SECONDS too small ({}) — clamping to 10", _RECIPIENT_REFRESH_S)
    _RECIPIENT_REFRESH_S = 10
if _MAX_QUEUE_SIZE < 10:
    logger.warning("ALERT_QUEUE_MAX_SIZE too small ({}) — clamping to 10", _MAX_QUEUE_SIZE)
    _MAX_QUEUE_SIZE = 10


# ── Pydantic model for AlertJob validation ────────────────────
class AlertJob(BaseModel):
    """
    Represents one alert dispatch job.
    
    # FIXED: Validation for all fields
    # IMPROVED: Optional frame_bgr with proper type hint
    """
    zone_id: str = Field(..., min_length=1, max_length=100)
    zone_name: str = Field(..., min_length=1, max_length=200)
    zone_type: str = Field(..., pattern="^(danger|restricted|safe|unknown)$")
    track_id: int = Field(..., ge=0)
    missing_ppe: List[str] = Field(default_factory=list)
    severity: str = Field(..., pattern="^(CRITICAL|HIGH|MEDIUM|LOW)$")
    timestamp: str = Field(..., min_length=1)  # ISO format expected
    frame_bgr: Optional[np.ndarray] = Field(default=None, exclude=True)  # Exclude from serialization
    
    class Config:
        arbitrary_types_allowed = True  # For numpy array
    
    @field_validator("missing_ppe", mode="before")
    @classmethod
    def validate_ppe_list(cls, v):
        if not v:
            return []
        return [str(item).strip() for item in v if item]

    @model_validator(mode="after")
    def validate_consistency(self) -> "AlertJob":
        if self.severity == "CRITICAL" and not self.missing_ppe:
            logger.warning("CRITICAL alert with no missing_ppe — auto-adding 'unknown'")
            self.missing_ppe = ["unknown"]
        return self


# ── Protocol for dependency injection ─────────────────────────
@runtime_checkable
class DBFactoryProtocol(Protocol):
    """Protocol for async session factory — enables mocking in tests."""
    def __call__(self): ...


class AlertWorker:
    """
    Background asyncio task that dispatches alerts.
    
    # IMPROVED: Thread pool for blocking cv2 operations
    # FIXED: Proper error handling with retry logic
    # IMPROVED: Metrics collection for monitoring
    """

    def __init__(self, max_queue_size: int = _MAX_QUEUE_SIZE) -> None:
        self._queue: asyncio.Queue[AlertJob] = asyncio.Queue(maxsize=max_queue_size)
        self._recipients: List[dict] = []
        self._last_refresh: float = 0.0
        self._task: Optional[asyncio.Task] = None
        self._db_factory: Optional[DBFactoryProtocol] = None
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="alert_encode")
        
        # Metrics (replace with Prometheus in prod)
        self._metrics = {
            "enqueued": 0, "dropped": 0, "sent": 0, "failed": 0, "throttled": 0
        }

    async def start(self, db_factory: DBFactoryProtocol) -> None:
        """Start the alert worker background task."""
        self._db_factory = db_factory
        await self._refresh_recipients()
        self._task = asyncio.create_task(self._worker_loop(), name="alert_worker")
        logger.info("Alert worker started | queue_size={}", _MAX_QUEUE_SIZE)

    async def stop(self) -> None:
        """Gracefully stop the worker."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._executor.shutdown(wait=False)
        logger.info("Alert worker stopped | metrics={}", self._metrics)

    async def enqueue(self, job: AlertJob | dict) -> bool:
        """
        Enqueue an alert job. Non-blocking — drops if queue full.
        
        # FIXED: Accept dict or AlertJob, validate/convert if needed
        """
        # Convert dict to AlertJob if needed
        if isinstance(job, dict):
            try:
                job = AlertJob(**job)
            except Exception as e:
                logger.error("Invalid alert job: {}", e)
                self._metrics["dropped"] += 1
                return False
        
        try:
            self._queue.put_nowait(job)
            self._metrics["enqueued"] += 1
            return True
        except asyncio.QueueFull:
            logger.warning("Alert queue full — dropping alert for zone={}", job.zone_id)
            self._metrics["dropped"] += 1
            return False

    def get_metrics(self) -> dict:
        """Return current metrics for monitoring endpoint."""
        return {
            **self._metrics,
            "queue_size": self._queue.qsize(),
            "recipients_count": len(self._recipients),
            "refresh_age_s": time.monotonic() - self._last_refresh,
        }

    async def _refresh_recipients(self) -> None:
        """Reload active recipients from PostgreSQL."""
        if self._db_factory is None:
            return
        from sqlalchemy import text
        try:
            async with self._db_factory() as session:
                result = await session.execute(
                    text("""
                        SELECT id, name, role, email, whatsapp_number,
                               notify_critical, notify_high,
                               notify_medium, notify_low,
                               zone_filter
                        FROM alert_recipients
                        WHERE active = 1
                        ORDER BY name
                    """)
                )
                self._recipients = [dict(row) for row in result.mappings().all()]
            self._last_refresh = time.monotonic()
            logger.info("Alert recipients refreshed: {}", len(self._recipients))
        except Exception as exc:
            logger.error("Failed to refresh alert recipients: {}", exc)

    def _recipient_wants_alert(self, recipient: dict, severity: str, zone_id: str) -> bool:
        """Check if this recipient should receive this alert."""
        severity_map = {
            "CRITICAL": recipient.get("notify_critical", True),
            "HIGH": recipient.get("notify_high", True),
            "MEDIUM": recipient.get("notify_medium", False),
            "LOW": recipient.get("notify_low", False),
        }
        if not severity_map.get(severity, False):
            return False

        zone_filter = recipient.get("zone_filter")
        if zone_filter:
            allowed = json.loads(zone_filter) if isinstance(zone_filter, str) else zone_filter
            if zone_id not in allowed:
                return False
        return True

    def _encode_frame_sync(self, frame_bgr: np.ndarray) -> Optional[bytes]:
        """
        Encode frame to JPEG bytes — runs in thread pool.
        
        # FIXED: Blocking cv2.imencode moved to sync method for executor
        """
        try:
            _, buf = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, _IMAGE_ENCODE_QUALITY])
            return buf.tobytes()
        except Exception as exc:
            logger.warning("Frame encoding failed: {}", exc)
            return None

    async def _encode_frame_async(self, frame_bgr: Optional[np.ndarray]) -> Optional[bytes]:
        """Async wrapper for frame encoding."""
        if frame_bgr is None:
            return None
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, self._encode_frame_sync, frame_bgr)

    async def _dispatch_to_recipient(
        self,
        recipient: dict,
        job: AlertJob,
        image_bytes: Optional[bytes],
    ) -> None:
        """Send alert to one recipient via all their configured channels."""
        r_id = recipient["id"]
        zone_id = job.zone_id
        track_id = job.track_id
        severity = job.severity

        if not self._recipient_wants_alert(recipient, severity, zone_id):
            return

        if not alert_throttle.should_send(r_id, zone_id, track_id, severity):
            logger.debug("Alert throttled | recipient={} | zone={} | severity={}", recipient["name"], zone_id, severity)
            await self._log_send(r_id, zone_id, track_id, severity, "throttled", None)
            self._metrics["throttled"] += 1
            return

        # Dispatch with retry logic
        results = []
        
        # WhatsApp
        if recipient.get("whatsapp_number"):
            success = False
            for attempt in range(_SEND_RETRY_ATTEMPTS):
                success = await send_whatsapp_alert(
                    to_number=recipient["whatsapp_number"],
                    zone_name=job.zone_name,
                    zone_type=job.zone_type,
                    track_id=track_id,
                    missing_ppe=job.missing_ppe,
                    severity=severity,
                    timestamp=job.timestamp,
                    image_bytes=image_bytes if attempt == 0 else None,  # Only attach on first try
                )
                if success:
                    break
                await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff
            
            await self._log_send(r_id, zone_id, track_id, severity, "sent" if success else "failed", "whatsapp")
            results.append(("whatsapp", success))

        # Email
        if recipient.get("email"):
            success = False
            for attempt in range(_SEND_RETRY_ATTEMPTS):
                success = await send_email_alert(
                    to_email=recipient["email"],
                    to_name=recipient["name"],
                    zone_name=job.zone_name,
                    zone_type=job.zone_type,
                    track_id=track_id,
                    missing_ppe=job.missing_ppe,
                    severity=severity,
                    timestamp=job.timestamp,
                    image_bytes=image_bytes if attempt == 0 else None,
                )
                if success:
                    break
                await asyncio.sleep(0.5 * (attempt + 1))
            
            await self._log_send(r_id, zone_id, track_id, severity, "sent" if success else "failed", "email")
            results.append(("email", success))

        # Record send if at least one channel succeeded
        if any(success for _, success in results):
            alert_throttle.record_send(r_id, zone_id, track_id, severity)
            self._metrics["sent"] += 1
        else:
            self._metrics["failed"] += 1

    async def _log_send(
        self,
        recipient_id: int,
        zone_id: str,
        track_id: int,
        severity: str,
        status: str,
        alert_type: Optional[str],
    ) -> None:
        """Write send log entry to PostgreSQL."""
        if self._db_factory is None:
            return
        from sqlalchemy import text
        from tenacity import retry, stop_after_attempt, wait_exponential
        
        @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=0.5, max=2))
        async def _persist():
            async with self._db_factory() as session:
                await session.execute(
                    text("""
                        INSERT INTO alert_send_log
                        (recipient_id, alert_type, zone_id, track_id, severity, status, created_at)
                        VALUES (:recipient_id, :alert_type, :zone_id, :track_id, :severity, :status, NOW())
                    """),
                    {
                        "recipient_id": recipient_id,
                        "alert_type": alert_type,
                        "zone_id": zone_id,
                        "track_id": track_id,
                        "severity": severity,
                        "status": status,
                    }
                )
                await session.commit()
        
        try:
            await _persist()
        except Exception as exc:
            logger.error("Alert log write failed: {}", exc)

    async def _worker_loop(self) -> None:
        """Main dispatch loop."""
        logger.info("Alert worker loop running")
        while True:
            try:
                # Periodically refresh recipient list
                if time.monotonic() - self._last_refresh > _RECIPIENT_REFRESH_S:
                    await self._refresh_recipients()

                job = await asyncio.wait_for(self._queue.get(), timeout=5.0)

                if not self._recipients:
                    logger.debug("No active recipients — alert dropped")
                    self._queue.task_done()
                    continue

                # Encode frame in thread pool (non-blocking)
                image_bytes = await self._encode_frame_async(job.frame_bgr)

                # Dispatch to all recipients concurrently with return_exceptions
                await asyncio.gather(
                    *(
                        self._dispatch_to_recipient(r, job, image_bytes)
                        for r in self._recipients
                    ),
                    return_exceptions=True,
                )

                self._queue.task_done()

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Alert worker error: {}", exc)
                await asyncio.sleep(5)


# ── Singleton with lazy initialization ────────────────────────
_alert_worker_instance: Optional[AlertWorker] = None


def get_alert_worker(max_queue_size: int = _MAX_QUEUE_SIZE) -> AlertWorker:
    """Get or create the alert worker singleton."""
    global _alert_worker_instance
    if _alert_worker_instance is None:
        _alert_worker_instance = AlertWorker(max_queue_size=max_queue_size)
    return _alert_worker_instance


# Backward compatibility alias
alert_worker = get_alert_worker()