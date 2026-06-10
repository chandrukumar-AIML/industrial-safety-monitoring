"""
backend/cache/__init__.py

Public API for the Redis cache layer.

# Usage:
    from backend.cache import redis_cache, RedisCache, RedisCacheContext
    from backend.cache import CacheError, CacheConnectionError  # Exceptions

# Example:
    async with RedisCacheContext() as cache:
        await cache.set_zones(zones_dict, camera_id="cam-01")
        zones = await cache.get_zones("cam-01")
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Type hints only — no runtime import cost
    from .redis_cache import RedisCache, RedisCacheContext, RedisClientProtocol
    from .redis_cache import CacheError, CacheConnectionError, CacheSerializationError

# ── Explicit public API ──────────────────────────────────────
__all__ = [
    # Core classes
    "RedisCache",
    "RedisCacheContext",
    
    # Singleton instance (lazy-initialized)
    "redis_cache",
    
    # Exceptions
    "CacheError",
    "CacheConnectionError", 
    "CacheSerializationError",
    
    # Protocol for testing
    "RedisClientProtocol",
    
    # Config helpers
    "get_cache_config",
    "validate_cache_config",
]

__version__ = "1.0.0"
__author__ = "Chandrukumar S"
__description__ = "Redis cache layer for Industrial Safety Monitor"


# ── Config helpers ───────────────────────────────────────────
def get_cache_config() -> dict:
    """Return current cache configuration (for diagnostics)."""
    from .redis_cache import (
        REDIS_URL, CACHE_NAMESPACE, REDIS_POOL_SIZE,
        ZONE_TTL, EMBEDDING_TTL, CANARY_TTL, DEDUP_TTL,
    )
    return {
        "redis_url": REDIS_URL,
        "namespace": CACHE_NAMESPACE,
        "pool_size": REDIS_POOL_SIZE,
        "ttls": {
            "zones": ZONE_TTL,
            "embedding": EMBEDDING_TTL,
            "canary": CANARY_TTL,
            "dedup": DEDUP_TTL,
        },
    }


def validate_cache_config() -> list[str]:
    """
    Validate cache config at startup.
    Returns list of warnings (empty = OK).
    """
    warnings = []
    
    # Check if Redis URL looks valid
    redis_url = os.getenv("REDIS_URL", "")
    if redis_url and not redis_url.startswith(("redis://", "rediss://", "unix://")):
        warnings.append(f"REDIS_URL may be invalid: {redis_url[:20]}...")
    
    # Warn if using default localhost in production
    if "localhost" in redis_url and os.getenv("ENVIRONMENT") == "production":
        warnings.append("Using localhost Redis in production — consider managed Redis")
    
    return warnings


# ── Lazy loader for heavy imports ────────────────────────────
def __getattr__(name: str) -> Any:
    """Lazy-load submodules only when accessed."""
    
    if name in ("RedisCache", "RedisCacheContext", "redis_cache"):
        from . import redis_cache as module
        return getattr(module, name)
    
    if name in ("CacheError", "CacheConnectionError", "CacheSerializationError"):
        from . import redis_cache as module
        return getattr(module, name)
    
    if name == "RedisClientProtocol":
        from . import redis_cache as module
        return getattr(module, name)
    
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


# ── Run validation at import (non-blocking warnings) ─────────
_cache_warnings = validate_cache_config()
if _cache_warnings and os.getenv("CACHE_STRICT_MODE", "false").lower() == "true":
    import warnings as _warnings
    for w in _cache_warnings:
        _warnings.warn(f"Cache config: {w}", RuntimeWarning, stacklevel=2)