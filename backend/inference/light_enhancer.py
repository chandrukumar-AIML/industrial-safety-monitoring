"""
inference/light_enhancer.py

Adaptive low-light frame enhancement.

# FIXED: CLAHE object reuse (no recreation per frame)
# FIXED: Input validation + bounds checking
# IMPROVED: Config validation at module load
# IMPROVED: Memory-efficient rolling history with deque
# FIXED: No PII leakage in logs

Inserted at the head of the inference pipeline — runs before
YOLOv8 sees each frame. Adds ~1ms per frame overhead.

Enhancement pipeline:
  1. Compute mean luminance (Y channel of YCrCb)
  2. Classify: NORMAL / LOW_LIGHT / VERY_DARK
  3. Apply CLAHE on luminance channel only (preserves colour)
  4. Apply adaptive gamma correction
  5. Merge back to BGR and return

Why luminance-only CLAHE:
  Applying CLAHE to all three BGR channels independently shifts
  colour balance and produces unnatural hues that confuse the
  PPE colour classifier (e.g. orange helmets appear yellow).
  Working only on the Y channel in YCrCb preserves hue and
  saturation while boosting perceived brightness.
"""

from __future__ import annotations

import os
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple, Dict, Any

import cv2
import numpy as np
from loguru import logger

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

ENABLED = os.getenv("LIGHT_ENHANCEMENT_ENABLED", "true").lower() == "true"
DARK_THRESHOLD = _validate_float_range("LIGHT_DARK_THRESHOLD", os.getenv("LIGHT_DARK_THRESHOLD", "80"), 80, 0, 255)
VERY_DARK_THRESH = _validate_float_range("LIGHT_VERY_DARK_THRESHOLD", os.getenv("LIGHT_VERY_DARK_THRESHOLD", "50"), 50, 0, DARK_THRESHOLD)
CLAHE_CLIP_LOW = _validate_float_range("LIGHT_CLAHE_CLIP_NORMAL", os.getenv("LIGHT_CLAHE_CLIP_NORMAL", "2.0"), 2.0, 1.0, 10.0)
CLAHE_CLIP_DARK = _validate_float_range("LIGHT_CLAHE_CLIP_DARK", os.getenv("LIGHT_CLAHE_CLIP_DARK", "3.5"), 3.5, 1.0, 10.0)
CLAHE_TILE = int(os.getenv("LIGHT_CLAHE_TILE_SIZE", "8"))
if not 4 <= CLAHE_TILE <= 16:
    logger.warning("LIGHT_CLAHE_TILE_SIZE invalid — using 8")
    CLAHE_TILE = 8
LOG_STATS = os.getenv("LIGHT_LOG_STATS", "false").lower() == "true"


class LightMode(Enum):
    NORMAL = "normal"
    LOW_LIGHT = "low_light"
    VERY_DARK = "very_dark"


@dataclass
class EnhancementStats:
    """Per-frame enhancement statistics for monitoring."""
    mode: LightMode
    mean_y_before: float
    mean_y_after: float
    gamma_applied: float
    clahe_applied: bool
    elapsed_ms: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode.value,
            "mean_y_before": self.mean_y_before,
            "mean_y_after": self.mean_y_after,
            "gamma_applied": self.gamma_applied,
            "clahe_applied": self.clahe_applied,
            "elapsed_ms": self.elapsed_ms,
        }


class LightEnhancer:
    """
    Adaptive low-light frame enhancer.

    # FIXED: CLAHE objects created once and reused
    # IMPROVED: deque(maxlen=30) for bounded brightness history
    # FIXED: Input validation + bounds checking
    # FIXED: No PII leakage in logs
    
    Usage:
        enhancer = LightEnhancer()
        enhanced_frame, stats = enhancer.process(frame_bgr)
        # Use enhanced_frame for inference, discard for display
    """

    def __init__(
        self,
        dark_threshold: float = DARK_THRESHOLD,
        very_dark_threshold: float = VERY_DARK_THRESH,
        clahe_clip_low: float = CLAHE_CLIP_LOW,
        clahe_clip_dark: float = CLAHE_CLIP_DARK,
        clahe_tile: int = CLAHE_TILE,
        history_len: int = 30,
    ) -> None:
        self._enabled = ENABLED
        self._dark_threshold = dark_threshold
        self._very_dark_threshold = very_dark_threshold
        self._history_len = history_len

        if not self._enabled:
            logger.info("LightEnhancer disabled")
            return

        # Pre-built CLAHE objects for each mode — created ONCE
        self._clahe_low = cv2.createCLAHE(
            clipLimit=clahe_clip_low,
            tileGridSize=(clahe_tile, clahe_tile),
        )
        self._clahe_dark = cv2.createCLAHE(
            clipLimit=clahe_clip_dark,
            tileGridSize=(max(4, clahe_tile - 2), max(4, clahe_tile - 2)),
        )

        # Bounded rolling brightness history
        self._brightness_history: deque = deque(maxlen=history_len)
        self._frame_count: int = 0

        # Stats for monitoring endpoint (bounded)
        self._stats_history: deque = deque(maxlen=300)

        logger.info(
            "LightEnhancer ready | dark_thresh={} | very_dark_thresh={} | "
            "clahe_clip=({},{}) | tile={} | history_len={}",
            dark_threshold, very_dark_threshold,
            clahe_clip_low, clahe_clip_dark, clahe_tile, history_len,
        )

    def _mean_luminance(self, frame_bgr: np.ndarray) -> float:
        """
        Compute mean Y (luminance) of frame.
        Uses YCrCb colour space — Y is true perceptual luminance.
        Returns value in [0, 255].
        """
        # Validate input
        if frame_bgr is None or frame_bgr.size == 0:
            return 128.0  # Default mid-gray
        if frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3:
            logger.warning("Invalid frame for luminance: {}", frame_bgr.shape)
            return 128.0
            
        ycrcb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2YCrCb)
        return float(ycrcb[:, :, 0].mean())

    def _classify(self, mean_y: float) -> LightMode:
        """Classify lighting condition from mean luminance."""
        if mean_y < self._very_dark_threshold:
            return LightMode.VERY_DARK
        if mean_y < self._dark_threshold:
            return LightMode.LOW_LIGHT
        return LightMode.NORMAL

    def _adaptive_gamma(self, mean_y: float, mode: LightMode) -> float:
        """
        Compute gamma correction value based on lighting level.
        Gamma < 1.0 → brighten (inverse gamma correction).
        Gamma = 1.0 → no change.
        """
        if mode == LightMode.NORMAL:
            return 1.0

        # Clamp mean_y to avoid division issues
        safe_y = max(5.0, min(255.0, mean_y))
        gamma = (safe_y / 128.0) ** 0.5

        # Clamp gamma to reasonable range
        if mode == LightMode.VERY_DARK:
            gamma = max(0.25, min(0.70, gamma))
        else:
            gamma = max(0.50, min(0.90, gamma))

        return round(gamma, 3)

    def _apply_gamma(self, frame_bgr: np.ndarray, gamma: float) -> np.ndarray:
        """
        Apply gamma correction via lookup table (LUT).
        LUT approach: O(256) precompute + O(n) apply — very fast.
        """
        if gamma == 1.0:
            return frame_bgr  # No-op
            
        inv_gamma = 1.0 / gamma
        lut = np.array([
            min(255, int((i / 255.0) ** inv_gamma * 255))
            for i in range(256)
        ], dtype=np.uint8)
        return cv2.LUT(frame_bgr, lut)

    def _apply_clahe(self, frame_bgr: np.ndarray, mode: LightMode) -> np.ndarray:
        """
        Apply CLAHE to luminance channel only.
        Preserves hue and saturation — avoids colour distortion.
        """
        clahe = (
            self._clahe_dark if mode == LightMode.VERY_DARK
            else self._clahe_low
        )

        # Work in YCrCb colour space
        ycrcb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2YCrCb)
        y, cr, cb = cv2.split(ycrcb)

        # Apply CLAHE only to Y channel
        y_enhanced = clahe.apply(y)

        # Merge and convert back
        enhanced_ycrcb = cv2.merge([y_enhanced, cr, cb])
        return cv2.cvtColor(enhanced_ycrcb, cv2.COLOR_YCrCb2BGR)

    def _denoise(self, frame_bgr: np.ndarray, mode: LightMode) -> np.ndarray:
        """
        Apply lightweight denoising for very dark frames.
        Very dark frames amplify sensor noise — a small blur helps.
        Only applied in VERY_DARK mode.
        """
        if mode != LightMode.VERY_DARK:
            return frame_bgr
        # Fast bilateral filter — preserves edges while reducing noise
        return cv2.bilateralFilter(frame_bgr, d=5, sigmaColor=50, sigmaSpace=50)

    def process(
        self,
        frame_bgr: np.ndarray,
    ) -> Tuple[np.ndarray, Optional[EnhancementStats]]:
        """
        Main enhancement pipeline.

        Args:
            frame_bgr: Input BGR frame from camera.

        Returns:
            (enhanced_frame, stats) where enhanced_frame is ready
            for YOLOv8 inference. If disabled or NORMAL, returns
            the original frame unchanged.

        Note:
            The returned frame should only be used for inference.
            For display/storage, use the original frame — enhancement
            can make some colours look oversaturated on screen.
        """
        if not self._enabled or frame_bgr is None or frame_bgr.size == 0:
            return frame_bgr, None

        # Validate frame
        if frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3:
            logger.warning("Invalid frame for enhancement: {}", frame_bgr.shape)
            return frame_bgr, None

        t0 = time.perf_counter()

        # 1. Classify lighting
        mean_y_before = self._mean_luminance(frame_bgr)
        mode = self._classify(mean_y_before)

        # Track history (bounded deque)
        self._brightness_history.append(mean_y_before)
        self._frame_count += 1

        if mode == LightMode.NORMAL:
            if LOG_STATS and self._frame_count % 30 == 0:
                logger.debug("LightEnhancer: NORMAL | mean_Y={:.1f}", mean_y_before)
            return frame_bgr, EnhancementStats(
                mode=mode,
                mean_y_before=mean_y_before,
                mean_y_after=mean_y_before,
                gamma_applied=1.0,
                clahe_applied=False,
                elapsed_ms=0.0,
            )

        # 2. CLAHE on luminance
        enhanced = self._apply_clahe(frame_bgr, mode)

        # 3. Gamma correction
        gamma = self._adaptive_gamma(mean_y_before, mode)
        enhanced = self._apply_gamma(enhanced, gamma)

        # 4. Denoise (very dark only)
        enhanced = self._denoise(enhanced, mode)

        mean_y_after = self._mean_luminance(enhanced)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        stats = EnhancementStats(
            mode=mode,
            mean_y_before=round(mean_y_before, 1),
            mean_y_after=round(mean_y_after, 1),
            gamma_applied=gamma,
            clahe_applied=True,
            elapsed_ms=round(elapsed_ms, 2),
        )
        self._stats_history.append(stats)

        if LOG_STATS:
            logger.debug(
                "LightEnhancer | mode={} | Y: {:.1f}→{:.1f} | "
                "gamma={} | dt={:.1f}ms",
                mode.value, mean_y_before, mean_y_after,
                gamma, elapsed_ms,
            )

        return enhanced, stats

    def get_recent_stats(self, n: int = 100) -> dict:
        """Summary of recent enhancement statistics."""
        history = list(self._stats_history)[-n:]
        if not history:
            return {"frame_count": 0, "modes": {}}

        modes = {}
        for s in history:
            modes[s.mode.value] = modes.get(s.mode.value, 0) + 1

        avg_elapsed = sum(s.elapsed_ms for s in history) / len(history)
        avg_y_before = sum(s.mean_y_before for s in history) / len(history)
        avg_y_after = sum(s.mean_y_after for s in history) / len(history)

        return {
            "frame_count": self._frame_count,
            "recent_frames": len(history),
            "mode_distribution": modes,
            "avg_elapsed_ms": round(avg_elapsed, 2),
            "avg_y_before": round(avg_y_before, 1),
            "avg_y_after": round(avg_y_after, 1),
            "avg_brightness_boost": round(avg_y_after - avg_y_before, 1),
        }

    def get_rolling_brightness(self) -> float:
        """Rolling mean brightness over last N frames."""
        if not self._brightness_history:
            return 128.0
        return round(sum(self._brightness_history) / len(self._brightness_history), 1)

    def is_currently_dark(self) -> bool:
        """True if rolling mean indicates low-light conditions."""
        return self.get_rolling_brightness() < self._dark_threshold

    def toggle(self, enabled: bool) -> None:
        """Enable or disable enhancement at runtime."""
        self._enabled = enabled
        logger.info("LightEnhancer toggled: {}", "on" if enabled else "off")

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def frame_count(self) -> int:
        return self._frame_count

    def get_diagnostics(self) -> dict:
        """Return enhancer status for health checks."""
        return {
            "enabled": self._enabled,
            "dark_threshold": self._dark_threshold,
            "very_dark_threshold": self._very_dark_threshold,
            "frame_count": self.frame_count,
            "rolling_brightness": self.get_rolling_brightness(),
            "recent_stats": self.get_recent_stats(10),
        }


# ── Singleton with lazy initialization ───────────────────────
_light_enhancer_instance: Optional[LightEnhancer] = None


def get_light_enhancer(**kwargs) -> LightEnhancer:
    """Get or create the light enhancer singleton."""
    global _light_enhancer_instance
    if _light_enhancer_instance is None:
        _light_enhancer_instance = LightEnhancer(**kwargs)
    return _light_enhancer_instance


# Backward compatibility alias
light_enhancer = get_light_enhancer()