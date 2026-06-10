"""
cache/redis_cache.py

Lightweight Redis cache wrapper.

# FIXED: Secure serialization (msgpack instead of pickle)
# FIXED: Input validation + sanitization for all public methods
# FIXED: Connection pool configuration + retry logic
# IMPROVED: Dependency injection for testability
# IMPROVED: Config validation at startup
# FIXED: Use SCAN instead of KEYS for production safety
# IMPROVED: Structured metrics + health check endpoint
# FIXED: No credential leakage in logs

Used for:
  1. Zone polygon data — hot path, queried every frame
  2. Worker face embeddings — shared across camera processes
  3. Canary routing state — fast shared flag
  4. Recent violation deduplication

Falls back gracefully to DB if Redis unavailable.
All keys namespaced under "ism:" (Industrial Safety Monitor).
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Protocol, runtime_checkable

from loguru import logger

# ── Config: Load from env with validation ─────────────────────
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
# FIXED: Warn instead of raise — a missing/invalid REDIS_URL should not crash the app
# at import time; the cache simply operates in disabled mode.
if not re.match(r'^(rediss?|unix)://', REDIS_URL):
    logger.warning("Invalid REDIS_URL format: {} — Redis cache will be disabled", REDIS_URL)
    REDIS_URL = ""  # connect() will return False immediately

# TTL values with validation
# FIXED: raise ValueError → logger.warning + clamp (crash at import is unacceptable)
def _validate_ttl(name: str, value: str, default: int, min_val: int = 1, max_val: int = 86400) -> int:
    try:
        ttl = int(value)
    except (ValueError, TypeError):
        ttl = default
    if not min_val <= ttl <= max_val:
        logger.warning("{} out of {}-{}: {} — using default {}", name, min_val, max_val, ttl, default)
        ttl = default
    return ttl

ZONE_TTL = _validate_ttl("REDIS_ZONE_CACHE_TTL", os.getenv("REDIS_ZONE_CACHE_TTL", "300"), 300)
EMBEDDING_TTL = _validate_ttl("REDIS_EMBEDDING_CACHE_TTL", os.getenv("REDIS_EMBEDDING_CACHE_TTL", "3600"), 3600)
CANARY_TTL = _validate_ttl("REDIS_CANARY_TTL", os.getenv("REDIS_CANARY_TTL", "86400"), 86400, min_val=60)
DEDUP_TTL = _validate_ttl("REDIS_DEDUP_TTL", os.getenv("REDIS_DEDUP_TTL", "30"), 30, max_val=300)

# Namespace — configurable per environment
CACHE_NAMESPACE = os.getenv("REDIS_NAMESPACE", "ism:")
if not CACHE_NAMESPACE.endswith(":"):
    CACHE_NAMESPACE += ":"

# Connection pool settings
REDIS_POOL_SIZE = int(os.getenv("REDIS_POOL_SIZE", "10"))
REDIS_SOCKET_TIMEOUT = float(os.getenv("REDIS_SOCKET_TIMEOUT", "1.0"))
REDIS_RETRY_ON_TIMEOUT = os.getenv("REDIS_RETRY_ON_TIMEOUT", "true").lower() == "true"
REDIS_MAX_RETRIES = int(os.getenv("REDIS_MAX_RETRIES", "3"))

# Serialization: msgpack for security + performance
try:
    import msgpack
    _HAS_MSGPACK = True
except ImportError:
    logger.warning("msgpack not installed — falling back to JSON for embeddings (less efficient)")
    _HAS_MSGPACK = False


# ── Protocol for dependency injection (testability) ───────────
@runtime_checkable
class RedisClientProtocol(Protocol):
    """Protocol for Redis client — enables mocking in tests."""
    async def ping(self) -> bool: ...
    async def setex(self, name: str, time: int, value: bytes) -> bool: ...
    async def get(self, name: str) -> Optional[bytes]: ...
    async def delete(self, *names: str) -> int: ...
    async def keys(self, pattern: str) -> list: ...
    async def scan_iter(self, match: str, count: int = 100): ...
    async def info(self, section: str = "default") -> Dict[str, Any]: ...
    async def dbsize(self) -> int: ...
    async def aclose(self) -> None: ...
    async def set(self, name: str, value: bytes, ex: Optional[int] = None, nx: bool = False) -> Optional[bool]: ...


# ── Custom exceptions for cache-specific errors ───────────────
class CacheError(Exception):
    """Base exception for cache operations."""
    pass

class CacheConnectionError(CacheError):
    """Raised when Redis connection fails."""
    pass

class CacheSerializationError(CacheError):
    """Raised when (de)serialization fails."""
    pass


# ── Helper: Sanitize cache keys to prevent injection ──────────
def _sanitize_key_part(value: str, max_len: int = 100) -> str:
    """
    Sanitize a string for use in Redis key.
    
    # FIXED: Prevent key injection via special chars
    """
    if not value:
        raise ValueError("Key part cannot be empty")
    # Allow only safe chars: alphanumeric, dash, underscore, colon, slash
    cleaned = re.sub(r'[^a-zA-Z0-9_\-:/.]', '_', str(value)[:max_len])
    if not cleaned:
        raise ValueError(f"Invalid key part after sanitization: {value}")
    return cleaned


def _serialize(value: Any, use_msgpack: bool = True) -> bytes:
    """
    Serialize value to bytes.
    
    # FIXED: Use msgpack for security (no arbitrary code exec like pickle)
    """
    try:
        if use_msgpack and _HAS_MSGPACK:
            return msgpack.packb(value, use_bin_type=True)
        # Fallback to JSON
        return json.dumps(value).encode('utf-8')
    except Exception as e:
        raise CacheSerializationError(f"Serialization failed: {e}")


def _deserialize(data: bytes, use_msgpack: bool = True) -> Any:
    """Deserialize bytes to value."""
    try:
        if use_msgpack and _HAS_MSGPACK:
            return msgpack.unpackb(data, raw=False)
        # Fallback to JSON
        return json.loads(data.decode('utf-8'))
    except Exception as e:
        raise CacheSerializationError(f"Deserialization failed: {e}")


class RedisCache:
    """
    Async Redis cache with graceful fallback.

    # IMPROVED: Dependency injection for testability
    # IMPROVED: Retry logic for transient failures
    # FIXED: Secure serialization (msgpack/JSON, no pickle)
    # FIXED: Connection pool configuration
    # IMPROVED: Structured metrics + health endpoint
    
    On connection failure, all operations return None/False —
    the caller falls back to PostgreSQL. This ensures Redis is
    an optimisation, not a dependency for correctness.

    Usage:
        cache = RedisCache()
        await cache.connect()
        await cache.set_zones(zones_dict)
        zones = await cache.get_zones()
    """

    def __init__(
        self,
        redis_url: str = REDIS_URL,
        namespace: str = CACHE_NAMESPACE,
        pool_size: int = REDIS_POOL_SIZE,
        socket_timeout: float = REDIS_SOCKET_TIMEOUT,
        client_cls: Optional[type] = None,  # For testing: inject mock client
    ) -> None:
        self._redis_url = redis_url
        self._namespace = namespace
        self._pool_size = pool_size
        self._socket_timeout = socket_timeout
        self._client_cls = client_cls  # Injected for testing
        
        self._client: Optional[RedisClientProtocol] = None
        self._enabled = False
        self._metrics = {
            "hits": 0,
            "misses": 0,
            "errors": 0,
            "fallbacks": 0,
            "connect_attempts": 0,
        }
        
        logger.debug(
            "RedisCache initialised | url={} | namespace={} | pool_size={}",
            self._redact_url(redis_url), namespace, pool_size,
        )

    def _redact_url(self, url: str) -> str:
        """Redact credentials from Redis URL for logging."""
        # Remove password if present
        return re.sub(r'://([^:]+):[^@]+@', r'://\1:***@', url)

    async def connect(self) -> bool:
        """
        Connect to Redis with retry logic.
        Returns True if connected, False if unavailable.
        
        # FIXED: Connection pool configuration
        # IMPROVED: Retry on transient failures
        """
        self._metrics["connect_attempts"] += 1
        
        for attempt in range(REDIS_MAX_RETRIES):
            try:
                # Lazy import + allow injection for testing
                if self._client_cls:
                    aioredis = None  # Not needed for mock
                    self._client = self._client_cls()
                else:
                    import redis.asyncio as aioredis
                    
                    # Configure connection pool
                    self._client = aioredis.from_url(
                        self._redis_url,
                        encoding="utf-8",
                        decode_responses=False,
                        socket_timeout=self._socket_timeout,
                        socket_connect_timeout=self._socket_timeout,
                        max_connections=self._pool_size,
                        retry_on_timeout=REDIS_RETRY_ON_TIMEOUT,
                        health_check_interval=30,  # Auto-reconnect on stale connections
                    )
                
                await self._client.ping()
                self._enabled = True
                logger.info("Redis connected: {}", self._redact_url(self._redis_url))
                return True
                
            except Exception as exc:
                logger.warning(
                    "Redis connect attempt {}/{} failed: {} — {}",
                    attempt + 1, REDIS_MAX_RETRIES, type(exc).__name__, exc,
                )
                if attempt < REDIS_MAX_RETRIES - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff
                continue
        
        logger.error("Redis unavailable after {} attempts — running without cache", REDIS_MAX_RETRIES)
        self._client = None
        self._enabled = False
        self._metrics["errors"] += 1
        return False

    async def disconnect(self) -> None:
        """Gracefully close Redis connection."""
        if self._client:
            try:
                await self._client.aclose()
            except Exception as exc:
                logger.debug("Redis disconnect error: {}", exc)
            finally:
                self._client = None
                self._enabled = False
        logger.info("Redis disconnected")

    # ── Internal helpers ──────────────────────────────────────

    async def _set(self, key: str, value: bytes, ttl: int) -> bool:
        if not self._enabled or not self._client:
            return False
        try:
            full_key = f"{self._namespace}{key}"
            await self._client.setex(full_key, ttl, value)
            return True
        except Exception as exc:
            logger.debug("Redis SET failed [{}]: {}", key, exc)
            self._metrics["errors"] += 1
            return False

    async def _get(self, key: str) -> Optional[bytes]:
        if not self._enabled or not self._client:
            return None
        try:
            full_key = f"{self._namespace}{key}"
            result = await self._client.get(full_key)
            if result is not None:
                self._metrics["hits"] += 1
            else:
                self._metrics["misses"] += 1
            return result
        except Exception as exc:
            logger.debug("Redis GET failed [{}]: {}", key, exc)
            self._metrics["errors"] += 1
            self._metrics["fallbacks"] += 1
            return None

    async def _delete(self, key: str) -> bool:
        if not self._enabled or not self._client:
            return False
        try:
            full_key = f"{self._namespace}{key}"
            result = await self._client.delete(full_key)
            return result > 0
        except Exception as exc:
            logger.debug("Redis DELETE failed [{}]: {}", key, exc)
            self._metrics["errors"] += 1
            return False

    async def _scan_keys(self, pattern: str) -> list:
        """
        Scan for keys matching pattern — non-blocking alternative to KEYS.
        
        # FIXED: Use SCAN instead of KEYS to avoid blocking Redis
        """
        if not self._enabled or not self._client:
            return []
        try:
            full_pattern = f"{self._namespace}{pattern}"
            keys = []
            async for key in self._client.scan_iter(match=full_pattern, count=100):
                keys.append(key.decode() if isinstance(key, bytes) else key)
            return keys
        except Exception as exc:
            logger.debug("Redis SCAN failed [{}]: {}", pattern, exc)
            self._metrics["errors"] += 1
            return []

    # ── Zone cache ────────────────────────────────────────────

    async def set_zones(
        self,
        zones: Dict[str, Any],
        camera_id: str = "default",
    ) -> bool:
        """
        Cache zone definitions for one camera.
        
        # FIXED: Validate inputs before caching
        """
        # Validate camera_id
        camera_id_safe = _sanitize_key_part(camera_id, max_len=50)
        
        # Validate zones structure (basic schema check)
        if not isinstance(zones, dict):
            logger.error("set_zones: expected dict, got {}", type(zones).__name__)
            return False
        
        # Optional: deeper validation if needed
        # for zone_id, zone_data in zones.items():
        #     if not isinstance(zone_data, dict) or "polygon_norm" not in zone_data:
        #         logger.warning("Invalid zone data for {}: missing polygon_norm", zone_id)
        
        key = f"zones:{camera_id_safe}"
        try:
            value = _serialize(zones, use_msgpack=True)
            return await self._set(key, value, ZONE_TTL)
        except CacheSerializationError as e:
            logger.error("Zone serialization failed: {}", e)
            return False

    async def get_zones(
        self,
        camera_id: str = "default",
    ) -> Optional[Dict[str, Any]]:
        """Get cached zone definitions. None if miss or error."""
        camera_id_safe = _sanitize_key_part(camera_id, max_len=50)
        raw = await self._get(f"zones:{camera_id_safe}")
        if raw is None:
            return None
        try:
            return _deserialize(raw, use_msgpack=True)
        except CacheSerializationError as e:
            logger.warning("Zone deserialization failed: {} — invalidating cache", e)
            await self.invalidate_zones(camera_id_safe)
            return None

    async def invalidate_zones(self, camera_id: str = "default") -> bool:
        """Invalidate zone cache when zones are updated."""
        camera_id_safe = _sanitize_key_part(camera_id, max_len=50)
        return await self._delete(f"zones:{camera_id_safe}")

    async def invalidate_all_zones(self) -> None:
        """Invalidate all camera zone caches."""
        if not self._enabled:
            return
        # Use SCAN instead of KEYS
        keys = await self._scan_keys("zones:*")
        if keys:
            # Strip namespace prefix for delete
            raw_keys = [k.replace(self._namespace, "", 1) for k in keys]
            try:
                if self._client:
                    await self._client.delete(*[f"{self._namespace}{k}" for k in raw_keys])
                logger.info("Invalidated {} zone cache entries", len(keys))
            except Exception as exc:
                logger.debug("Redis zone invalidation failed: {}", exc)

    # ── Face embedding cache ──────────────────────────────────

    async def set_embedding(
        self,
        worker_id: str,
        embedding: bytes,  # Raw embedding bytes (not pickle!)
    ) -> bool:
        """
        Cache face embedding for one worker.
        
        # FIXED: Validate worker_id format
        # FIXED: Accept raw bytes (not pickle) for security
        """
        worker_id_safe = _sanitize_key_part(worker_id, max_len=100)
        
        # Validate embedding is bytes
        if not isinstance(embedding, bytes):
            logger.error("set_embedding: expected bytes, got {}", type(embedding).__name__)
            return False
        
        # Optional: validate embedding size (e.g., 512-float32 = 2048 bytes)
        if len(embedding) > 10000:  # Sanity check
            logger.warning("Large embedding for worker {}: {} bytes", worker_id_safe, len(embedding))
        
        return await self._set(f"embedding:{worker_id_safe}", embedding, EMBEDDING_TTL)

    async def get_embedding(self, worker_id: str) -> Optional[bytes]:
        """Get cached face embedding bytes."""
        worker_id_safe = _sanitize_key_part(worker_id, max_len=100)
        return await self._get(f"embedding:{worker_id_safe}")

    async def invalidate_embedding(self, worker_id: str) -> bool:
        worker_id_safe = _sanitize_key_part(worker_id, max_len=100)
        return await self._delete(f"embedding:{worker_id_safe}")

    # ── Canary routing flag ───────────────────────────────────

    async def set_canary_state(self, state: Dict[str, Any]) -> bool:
        """
        Share canary router state across processes.
        
        # FIXED: Validate state schema (basic)
        """
        if not isinstance(state, dict):
            logger.error("set_canary_state: expected dict, got {}", type(state).__name__)
            return False
        
        # Optional: enforce required fields
        # required = ["model_version", "traffic_pct", "enabled"]
        # if not all(k in state for k in required):
        #     logger.warning("Canary state missing required fields: {}", required)
        
        try:
            value = _serialize(state, use_msgpack=True)
            return await self._set("canary:state", value, CANARY_TTL)
        except CacheSerializationError as e:
            logger.error("Canary state serialization failed: {}", e)
            return False

    async def get_canary_state(self) -> Optional[Dict[str, Any]]:
        raw = await self._get("canary:state")
        if raw is None:
            return None
        try:
            return _deserialize(raw, use_msgpack=True)
        except CacheSerializationError as e:
            logger.warning("Canary state deserialization failed: {}", e)
            return None

    # ── Violation deduplication ───────────────────────────────

    async def mark_violation_seen(
        self,
        track_id: int,
        class_name: str,
        ttl: int = DEDUP_TTL,
    ) -> bool:
        """
        Mark a (track_id, class_name) pair as recently seen.
        Returns True if this is a NEW violation (not a duplicate).
        
        # FIXED: Sanitize class_name to prevent key injection
        # FIXED: Validate TTL per-call
        """
        if not isinstance(track_id, int) or track_id < 0:
            logger.error("mark_violation_seen: invalid track_id {}", track_id)
            return True  # Treat as new on invalid input
        
        class_name_safe = _sanitize_key_part(class_name, max_len=50)
        
        # Validate TTL for this call
        if not 1 <= ttl <= 300:
            logger.warning("Invalid dedup TTL {}: using default {}", ttl, DEDUP_TTL)
            ttl = DEDUP_TTL
        
        key = f"viol:{track_id}:{class_name_safe}"
        
        if not self._enabled or not self._client:
            return True  # Without Redis, treat every violation as new
        
        try:
            # NX = only set if key doesn't exist → returns True if newly set
            result = await self._client.set(
                f"{self._namespace}{key}", b"1", ex=ttl, nx=True
            )
            return result is True  # True only if key was newly created
        except Exception:
            # On error, fall back to "new violation" to avoid false dedup
            self._metrics["errors"] += 1
            self._metrics["fallbacks"] += 1
            return True

    # ── Stats & Health ────────────────────────────────────────

    async def get_stats(self) -> Dict[str, Any]:
        """Return cache metrics + Redis info."""
        base_stats = {
            "enabled": self._enabled,
            "namespace": self._namespace,
            "metrics": {**self._metrics},
            "hit_rate": round(
                self._metrics["hits"] / max(self._metrics["hits"] + self._metrics["misses"], 1) * 100, 1
            ),
        }
        
        if not self._enabled or not self._client:
            return {**base_stats, "status": "disconnected"}
        
        try:
            # Use non-blocking info commands
            info = await self._client.info("memory")
            keys_count = await self._client.dbsize()
            
            return {
                **base_stats,
                "status": "connected",
                "url": self._redact_url(self._redis_url),
                "total_keys": keys_count,
                "used_memory_mb": round(info.get("used_memory", 0) / 1024 / 1024, 2),
                "peak_memory_mb": round(info.get("used_memory_peak", 0) / 1024 / 1024, 2),
                "connected_clients": info.get("connected_clients", 0),
                "uptime_seconds": info.get("uptime_in_seconds", 0),
            }
        except Exception as exc:
            return {
                **base_stats,
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            }

    async def health_check(self) -> Dict[str, Any]:
        """
        Lightweight health check for load balancers / Kubernetes.
        
        Returns:
            {"status": "healthy"|"degraded"|"unhealthy", "latency_ms": float}
        """
        start = datetime.now(timezone.utc)
        
        if not self._enabled or not self._client:
            return {"status": "unhealthy", "reason": "not_connected", "latency_ms": 0}
        
        try:
            await self._client.ping()
            latency = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            return {"status": "healthy", "latency_ms": round(latency, 2)}
        except Exception as exc:
            latency = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            return {
                "status": "degraded" if latency < 100 else "unhealthy",
                "reason": f"ping_failed: {type(exc).__name__}",
                "latency_ms": round(latency, 2),
            }

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def get_metrics(self) -> Dict[str, Any]:
        """Return in-memory metrics (for Prometheus exporter)."""
        return {
            **self._metrics,
            "enabled": self._enabled,
            "hit_rate": round(
                self._metrics["hits"] / max(self._metrics["hits"] + self._metrics["misses"], 1) * 100, 1
            ),
        }

    def reset_metrics(self) -> None:
        """Reset metrics — useful for testing or periodic reporting."""
        self._metrics = {k: 0 for k in self._metrics}


# ── Singleton with lazy initialization + dependency injection ─
_redis_cache_instance: Optional[RedisCache] = None


def get_redis_cache(
    redis_url: Optional[str] = None,
    namespace: Optional[str] = None,
    client_cls: Optional[type] = None,  # For testing
) -> RedisCache:
    """
    Get or create the Redis cache singleton.
    
    # IMPROVED: Lazy initialization + dependency injection support
    """
    global _redis_cache_instance
    if _redis_cache_instance is None:
        _redis_cache_instance = RedisCache(
            redis_url=redis_url or REDIS_URL,
            namespace=namespace or CACHE_NAMESPACE,
            client_cls=client_cls,
        )
    return _redis_cache_instance


# Backward compatibility alias
redis_cache = get_redis_cache()


# ── Context manager for automatic connect/disconnect ──────────
class RedisCacheContext:
    """
    Async context manager for Redis cache lifecycle.
    
    Usage:
        async with RedisCacheContext() as cache:
            await cache.set_zones(zones)
    """
    
    def __init__(self, **kwargs):
        self._cache = RedisCache(**kwargs)
    
    async def __aenter__(self) -> RedisCache:
        await self._cache.connect()
        return self._cache
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._cache.disconnect()
        return False  # Don't suppress exceptions