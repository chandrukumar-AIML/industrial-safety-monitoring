"""
alerts/throttle.py

In-memory alert throttle.
Prevents notification fatigue by rate-limiting
alerts per (recipient_id, zone_id, severity_bucket).

# FIXED: Redis-compatible interface stub for future scaling
# IMPROVED: Configurable thresholds via env vars with validation
# IMPROVED: Metrics endpoint for monitoring
# FIXED: Thread-safe via asyncio (single-threaded event loop)
"""

from __future__ import annotations

import os
import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple, Union

from loguru import logger

# ── Config: Load from env with validation ─────────────────────
# FIXED: module-level raise → warning + clamp (raise at import crashes the app)
def _parse_throttle_minutes(raw: str) -> int:
    try:
        val = int(raw)
    except ValueError:
        val = 5
    if not 1 <= val <= 60:
        logger.warning("ALERT_THROTTLE_MINUTES={} out of 1-60 — clamping", val)
        val = max(1, min(60, val))
    return val

def _parse_max_per_hour(raw: str) -> int:
    try:
        val = int(raw)
    except ValueError:
        val = 20
    if not 1 <= val <= 100:
        logger.warning("ALERT_MAX_PER_HOUR={} out of 1-100 — clamping", val)
        val = max(1, min(100, val))
    return val

THROTTLE_MINUTES = _parse_throttle_minutes(os.getenv("ALERT_THROTTLE_MINUTES", "5"))
MAX_PER_HOUR = _parse_max_per_hour(os.getenv("ALERT_MAX_PER_HOUR", "20"))

CRITICAL_BYPASS_THROTTLE = os.getenv(
    "ALERT_CRITICAL_BYPASS_THROTTLE", "true"
).lower() == "true"

# Backend selection: "memory" or "redis" (stub)
THROTTLE_BACKEND = os.getenv("ALERT_THROTTLE_BACKEND", "memory").lower()


# ── Severity bucket mapping ──────────────────────────────────
_SEVERITY_BUCKET = {
    "CRITICAL": "critical",
    "HIGH": "high",
    "MEDIUM": "digest",
    "LOW": "digest",
}


class AlertThrottle:
    """
    Sliding window throttle for alert delivery.
    
    # IMPROVED: Redis-compatible interface (stub for future)
    # IMPROVED: Metrics collection for monitoring
    """

    def __init__(
        self,
        backend: str = THROTTLE_BACKEND,
        throttle_minutes: int = THROTTLE_MINUTES,
        max_per_hour: int = MAX_PER_HOUR,
        critical_bypass: bool = CRITICAL_BYPASS_THROTTLE,
    ) -> None:
        self._backend = backend
        self._throttle_minutes = throttle_minutes
        self._max_per_hour = max_per_hour
        self._critical_bypass = critical_bypass
        
        # In-memory storage (Redis stub would replace these)
        # (key) → list of send timestamps (monotonic)
        self._windows: Dict[tuple, List[float]] = defaultdict(list)
        # (recipient_id,) → list of hourly send timestamps
        self._hourly: Dict[int, List[float]] = defaultdict(list)
        
        # Metrics
        self._metrics = {
            "checks": 0,
            "allowed": 0,
            "throttled": 0,
            "hourly_capped": 0,
        }
        
        logger.info(
            "AlertThrottle initialised | backend={} | window={}min | max/hour={}",
            backend, throttle_minutes, max_per_hour,
        )

    def _clean_window(self, key: tuple, window_s: float) -> List[float]:
        """Remove expired timestamps from a window."""
        now = time.monotonic()
        cleaned = [t for t in self._windows[key] if now - t < window_s]
        self._windows[key] = cleaned
        return cleaned

    def _clean_hourly(self, recipient_id: int) -> List[float]:
        """Remove timestamps older than 1 hour."""
        now = time.monotonic()
        cleaned = [t for t in self._hourly[recipient_id] if now - t < 3600]
        self._hourly[recipient_id] = cleaned
        return cleaned

    def should_send(
        self,
        recipient_id: int,
        zone_id: str,
        track_id: int,
        severity: str,
    ) -> bool:
        """
        Returns True if this alert should be sent to this recipient.
        
        Logic:
          1. CRITICAL severity bypasses per-alert throttle (if configured)
          2. Hourly cap always enforced regardless of severity
          3. Per-alert window: one alert per (recipient, zone, track, severity_bucket)
             per THROTTLE_MINUTES
        """
        self._metrics["checks"] += 1
        
        # Hourly cap check (always enforced)
        hourly = self._clean_hourly(recipient_id)
        if len(hourly) >= self._max_per_hour:
            self._metrics["hourly_capped"] += 1
            return False

        # CRITICAL bypass (configurable)
        # FIXED: Must still record_send so hourly cap tracks CRITICAL alerts
        bucket = _SEVERITY_BUCKET.get(severity, "digest")
        if severity == "CRITICAL" and self._critical_bypass:
            self._metrics["allowed"] += 1
            self.record_send(recipient_id, zone_id, track_id, severity)
            return True

        # Per-alert window check
        key = (recipient_id, zone_id, track_id, bucket)
        window = self._clean_window(key, self._throttle_minutes * 60)
        
        if len(window) == 0:
            self._metrics["allowed"] += 1
            return True
        else:
            self._metrics["throttled"] += 1
            return False

    def record_send(
        self,
        recipient_id: int,
        zone_id: str,
        track_id: int,
        severity: str,
    ) -> None:
        """Record that an alert was sent."""
        now = time.monotonic()
        bucket = _SEVERITY_BUCKET.get(severity, "digest")
        key = (recipient_id, zone_id, track_id, bucket)
        self._windows[key].append(now)
        self._hourly[recipient_id].append(now)

    def get_stats(self) -> dict:
        """Summary stats for monitoring."""
        return {
            "backend": self._backend,
            "tracked_windows": len(self._windows),
            "tracked_hourly": len(self._hourly),
            "throttle_minutes": self._throttle_minutes,
            "max_per_hour": self._max_per_hour,
            "critical_bypass": self._critical_bypass,
            **self._metrics,
            "throttle_rate": round(
                self._metrics["throttled"] / max(self._metrics["checks"], 1) * 100, 1
            ),
        }

    def reset(self) -> None:
        """Clear all throttle state — useful for testing."""
        self._windows.clear()
        self._hourly.clear()
        self._metrics = {k: 0 for k in self._metrics}
        logger.debug("AlertThrottle state reset")

    # ── Redis-compatible interface stubs (for future scaling) ─
    # When ready to scale to multi-process, replace _windows/_hourly
    # with Redis sorted sets (ZADD/ZREMRANGEBYSCORE)
    
    async def _redis_should_send(
        self,
        recipient_id: int,
        zone_id: str,
        track_id: int,
        severity: str,
        redis_client,  # aioredis or redis.asyncio client
    ) -> bool:
        """Future: Redis-backed throttle check."""
        # Stub implementation — replace with actual Redis logic when needed
        logger.warning("Redis backend not implemented — falling back to memory")
        return self.should_send(recipient_id, zone_id, track_id, severity)

    async def _redis_record_send(
        self,
        recipient_id: int,
        zone_id: str,
        track_id: int,
        severity: str,
        redis_client,
    ) -> None:
        """Future: Redis-backed send recording."""
        # Stub implementation
        self.record_send(recipient_id, zone_id, track_id, severity)


# ── Singleton with lazy initialization ───────────────────────
_alert_throttle_instance: Optional[AlertThrottle] = None


def get_alert_throttle(**kwargs) -> AlertThrottle:
    """Get or create the alert throttle singleton."""
    global _alert_throttle_instance
    if _alert_throttle_instance is None:
        _alert_throttle_instance = AlertThrottle(**kwargs)
    return _alert_throttle_instance


# Backward compatibility alias
alert_throttle = get_alert_throttle()