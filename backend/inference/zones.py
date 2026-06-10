"""
inference/zones.py

Loads zone polygon definitions from a YAML config and registers
them with both the tracker and the heatmap generator.

# FIXED: YAML parsing safety + input validation
# FIXED: Polygon validation (vertex count, dimensions)
# IMPROVED: Config validation at module load
# IMPROVED: Dependency injection via Protocol for testability
# FIXED: No PII leakage in logs
"""

from __future__ import annotations

import os
import pathlib
import re
from typing import Protocol, runtime_checkable, Dict, List, Optional, Any

import numpy as np
import yaml
from loguru import logger

# ── Lightweight protocols — no heavyweight imports needed ──────
@runtime_checkable
class ZoneRegistrar(Protocol):
    """Any object that can register / unregister / clear named polygon zones."""
    def register_zone(self, zone_id: str, polygon: np.ndarray) -> None: ...
    def unregister_zone(self, zone_id: str) -> None: ...
    def clear_zones(self) -> None: ...


# ── Validation constants ───────────────────────────────────────
_MIN_VERTICES: int = 3
_VERTEX_DIMS: int = 2
_MAX_ZONE_ID_LEN: int = 100
_ALLOWED_ZONE_ID_CHARS = re.compile(r'^[a-zA-Z0-9_\-]+$')


# ── Config: Load from env with validation ─────────────────────
ALLOWED_ZONES_DIRS = os.getenv("ALLOWED_ZONES_DIRS", "./config").split(",")
ALLOWED_ZONES_DIRS = [os.path.abspath(d.strip()) for d in ALLOWED_ZONES_DIRS if d.strip()]


# ── Internal helpers ───────────────────────────────────────────

def _validate_zone_path(config_path: str | pathlib.Path) -> pathlib.Path:
    """Validate and sanitize zone config path."""
    path = pathlib.Path(config_path).resolve()
    
    # Prevent path traversal
    if not any(str(path).startswith(d) for d in ALLOWED_ZONES_DIRS):
        raise ValueError(f"Zone config path not in allowed directories: {path}")
    
    return path


def _parse_zone(zone_def: dict) -> tuple[str, np.ndarray] | None:
    """
    Validate and parse a single zone definition dict from YAML.
    Returns (zone_id, polygon) on success, or None if invalid.
    """
    if not isinstance(zone_def, dict):
        logger.warning("Zone definition must be a dict — skipping: {}", type(zone_def).__name__)
        return None
        
    if "id" not in zone_def:
        logger.warning("Zone definition missing 'id' key — skipping: {}", zone_def)
        return None
    if "polygon" not in zone_def:
        logger.warning("Zone '{}' missing 'polygon' key — skipping", zone_def["id"])
        return None

    zone_id = zone_def["id"]

    # Validate zone_id format
    if not isinstance(zone_id, str) or not zone_id.strip():
        logger.warning("Zone id must be a non-empty string, got {!r} — skipping", zone_id)
        return None
    if len(zone_id) > _MAX_ZONE_ID_LEN:
        logger.warning("Zone id too long (max {}): {} — skipping", _MAX_ZONE_ID_LEN, zone_id)
        return None
    if not _ALLOWED_ZONE_ID_CHARS.match(zone_id):
        logger.warning("Zone id contains invalid chars: {} — skipping", zone_id)
        return None

    # Parse and validate polygon
    try:
        polygon = np.array(zone_def["polygon"], dtype=np.int32)
    except (ValueError, TypeError) as exc:
        logger.warning("Zone '{}' polygon could not be converted to array: {} — skipping", zone_id, exc)
        return None

    if polygon.ndim != 2:
        logger.warning("Zone '{}' polygon must be 2-D (N×2), got ndim={} — skipping", zone_id, polygon.ndim)
        return None
    if polygon.shape[1] != _VERTEX_DIMS:
        logger.warning("Zone '{}' each vertex must have {} coordinates, got {} — skipping", zone_id, _VERTEX_DIMS, polygon.shape[1])
        return None
    if len(polygon) < _MIN_VERTICES:
        logger.warning("Zone '{}' polygon must have >= {} vertices, got {} — skipping", zone_id, _MIN_VERTICES, len(polygon))
        return None
    
    # Validate coordinate ranges (should be pixel coords)
    if np.any(polygon < 0) or np.any(polygon > 10000):  # Reasonable pixel bounds
        logger.warning("Zone '{}' polygon has out-of-range coordinates — skipping", zone_id)
        return None

    return zone_id, polygon


# ── Public API ────────────────────────────────────────────────

def load_zones(
    config_path: str | pathlib.Path,
    tracker: ZoneRegistrar,
    heatmap: ZoneRegistrar,
) -> Dict[str, np.ndarray]:
    """
    Read zones.yaml and register each valid polygon with the
    tracker and heatmap. Invalid definitions are skipped with a warning.

    zones.yaml format:
        zones:
          - id: "zone-entrance"
            polygon: [[0,0],[320,0],[320,720],[0,720]]

    Args:
        config_path: Path to YAML config file.
        tracker: Object implementing ZoneRegistrar protocol.
        heatmap: Object implementing ZoneRegistrar protocol.

    Returns:
        dict mapping zone_id → polygon (successfully registered zones only).
        
    Raises:
        ValueError: If config_path is not in allowed directories.
    """
    # Validate path
    path = _validate_zone_path(config_path)
    
    if not path.exists():
        logger.warning("zones config not found at '{}' — no zones registered", path)
        return {}

    try:
        with path.open(encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        logger.error("Failed to parse YAML at '{}': {} — no zones registered", path, exc)
        return {}
    except OSError as exc:
        logger.error("Cannot read zones config '{}': {} — no zones registered", path, exc)
        return {}

    if cfg is None:
        logger.warning("'{}' is empty — no zones registered", path)
        return {}
    
    if not isinstance(cfg, dict) or "zones" not in cfg:
        logger.warning("'{}' missing 'zones' key — no zones registered", path)
        return {}

    registered: Dict[str, np.ndarray] = {}

    for i, zone_def in enumerate(cfg.get("zones", [])):
        parsed = _parse_zone(zone_def)
        if parsed is None:
            continue

        zone_id, polygon = parsed

        if zone_id in registered:
            logger.warning("Duplicate zone id '{}' in config — skipping second definition", zone_id)
            continue

        try:
            tracker.register_zone(zone_id, polygon)
            heatmap.register_zone(zone_id, polygon)
            registered[zone_id] = polygon
            logger.info("Zone registered: '{}' | vertices={}", zone_id, len(polygon))
        except Exception as exc:
            logger.error("Failed to register zone '{}': {} — skipping", zone_id, exc)
            continue

    if not registered:
        logger.warning("No valid zones found in '{}'", path)

    return registered


def validate_zones_config(config_path: str | pathlib.Path) -> List[str]:
    """
    Validate zones config without loading.
    Returns list of warnings (empty = OK).
    """
    warnings = []
    
    try:
        path = _validate_zone_path(config_path)
    except ValueError as e:
        return [str(e)]
    
    if not path.exists():
        warnings.append(f"Zones config not found: {path}")
        return warnings
    
    try:
        with path.open(encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        return [f"YAML parse error: {exc}"]
    except OSError as exc:
        return [f"Cannot read file: {exc}"]
    
    if cfg is None:
        warnings.append("Config file is empty")
        return warnings
    
    zones = cfg.get("zones", [])
    if not isinstance(zones, list):
        warnings.append("'zones' must be a list")
        return warnings
    
    valid_count = 0
    for i, zone_def in enumerate(zones):
        if not isinstance(zone_def, dict):
            warnings.append(f"Zone {i}: must be a dict")
            continue
        if "id" not in zone_def:
            warnings.append(f"Zone {i}: missing 'id'")
            continue
        if "polygon" not in zone_def:
            warnings.append(f"Zone '{zone_def['id']}': missing 'polygon'")
            continue
        valid_count += 1
    
    if valid_count == 0 and len(zones) > 0:
        warnings.append("No valid zones found in config")
    
    return warnings


# ── Convenience: Reload zones at runtime ──────────────────────
async def reload_zones(
    config_path: str | pathlib.Path,
    tracker: ZoneRegistrar,
    heatmap: ZoneRegistrar,
) -> Dict[str, np.ndarray]:
    """
    Reload zones from config, clearing existing zones first.
    Useful for hot-reload via API.
    
    Returns:
        dict of newly registered zones.
    """
    # Clear existing zones first
    tracker.clear_zones()
    heatmap.clear_zones()
    
    # Load new zones
    return load_zones(config_path, tracker, heatmap)