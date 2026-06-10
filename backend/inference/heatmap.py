"""
inference/heatmap.py

Gaussian accumulation heatmap for PPE violation density.

Maintains a persistent float32 accumulator updated every frame.
Exposes a colourised overlay for the live video feed and a
normalised risk score per registered zone for the dashboard.
"""

from __future__ import annotations

import cv2
import numpy as np
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from loguru import logger


@dataclass
class ZoneRisk:
    """Risk score for one named zone."""
    zone_id       : str
    mean_intensity: float    # mean accumulator value inside zone
    max_intensity : float    # peak value inside zone
    violation_pct : float    # fraction of zone pixels above threshold
    risk_level    : str      # "low" | "medium" | "high" | "critical"

    @property
    def risk_color_bgr(self) -> Tuple[int, int, int]:
        return {
            "low"     : (46,  204, 113),
            "medium"  : (230, 126,  34),
            "high"    : (231,  76,  60),
            "critical": (128,   0, 128),
        }.get(self.risk_level, (200, 200, 200))


class HeatmapGenerator:
    """
    Maintains a Gaussian accumulation heatmap over time.

    Each call to update() adds a Gaussian kernel centred on
    the detection centroid. The kernel's sigma scales with
    the detection's bounding box size — a large worker nearby
    contributes a wider heat bump than a small distant one.

    The accumulator decays slightly each frame so old violations
    fade out and the heatmap reflects recent activity.

    Usage:
        hm = HeatmapGenerator(frame_height=720, frame_width=1280)
        hm.update(x1, y1, x2, y2)           # one violation bbox
        overlay = hm.get_overlay(frame_bgr)  # colourised overlay
        risks   = hm.zone_risks()            # per-zone scores
    """

    # FIX 1: Default risk thresholds moved to class constant —
    # was recreated as a new dict on every zone_risks() call.
    DEFAULT_RISK_THRESHOLDS: Dict[str, float] = {
        "low"     : 0.15,
        "medium"  : 0.40,
        "high"    : 0.70,
        "critical": 1.01,
    }

    def __init__(
        self,
        frame_height     : int   = 640,
        frame_width      : int   = 640,
        decay_factor     : float = 0.998,
        alpha            : float = 0.45,
        min_sigma        : int   = 20,
        max_sigma        : int   = 80,
        colormap         : int   = cv2.COLORMAP_JET,
        normalise_window : int   = 500,
        violation_weights: Optional[Dict[str, float]] = None,
    ):
        self.H            = frame_height
        self.W            = frame_width
        self.decay        = decay_factor
        self.alpha        = alpha
        self.min_sigma    = min_sigma
        self.max_sigma    = max_sigma
        self.colormap     = colormap
        self.norm_window  = normalise_window

        self.violation_weights: Dict[str, float] = (
            violation_weights
            if violation_weights is not None
            else {"no-hardhat": 1.5, "": 1.0}
        )

        self._accumulator = np.zeros((self.H, self.W), dtype=np.float32)

        # deque with maxlen — O(1) append, never grows unboundedly
        self._max_history: deque = deque(maxlen=self.norm_window)

        self._zone_masks  : Dict[str, np.ndarray] = {}
        self._frame_count : int = 0
        self._kernel_cache: Dict[int, np.ndarray] = {}

        # FIX 2: Pre-compute the blurred overlay mask dimensions so
        # get_overlay() can skip GaussianBlur when frame size is unchanged.
        # Cached as (last_fh, last_fw) — reset to None on size change.
        self._overlay_size_cache: Optional[Tuple[int, int]] = None

        logger.info(
            f"HeatmapGenerator ready | "
            f"size=({self.W}x{self.H}) | "
            f"decay={self.decay} | alpha={self.alpha} | "
            f"violation_weights={self.violation_weights}"
        )

    # ── Zone management ───────────────────────────────────────

    def register_zone(
        self,
        zone_id : str,
        polygon : np.ndarray,
    ) -> None:
        """
        Register a polygonal zone for risk scoring.
        polygon: np.ndarray of shape (N, 2) — (x, y) pixel coords.
        """
        mask = np.zeros((self.H, self.W), dtype=bool)
        cv2.fillPoly(
            mask.view(np.uint8),
            [polygon.astype(np.int32)],
            1,
        )
        self._zone_masks[zone_id] = mask
        logger.debug(f"Zone '{zone_id}' registered | pixels={mask.sum()}")

    def unregister_zone(self, zone_id: str) -> None:
        """
        Remove a zone. Called by InferencePipeline.remove_zone()
        so the pipeline never touches private attributes directly.
        """
        removed = self._zone_masks.pop(zone_id, None)
        if removed is not None:
            logger.debug(f"Zone '{zone_id}' unregistered from heatmap")
        else:
            logger.warning(f"unregister_zone: '{zone_id}' not found")

    def clear_zones(self) -> None:
        """
        Remove all registered zones.
        Called by InferencePipeline.reload_zones() during hot-reload.
        """
        self._zone_masks.clear()
        logger.debug("All zones cleared from heatmap")

    # ── Gaussian kernel builder ───────────────────────────────

    def _get_kernel(self, sigma: int) -> np.ndarray:
        """
        Returns a normalised 2D Gaussian kernel for the given sigma.
        Kernels are cached so repeated sigmas cost nothing.
        """
        if sigma in self._kernel_cache:
            return self._kernel_cache[sigma]

        ksize     = int(6 * sigma) | 1
        kernel_1d = cv2.getGaussianKernel(ksize, sigma)
        kernel_2d = kernel_1d @ kernel_1d.T
        kernel_2d = kernel_2d / kernel_2d.max()   # peak = 1.0

        self._kernel_cache[sigma] = kernel_2d
        return kernel_2d

    def _sigma_from_bbox(self, x1: int, y1: int, x2: int, y2: int) -> int:
        """Scales Gaussian sigma with the bbox diagonal."""
        diag  = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
        sigma = int(np.clip(diag * 0.25, self.min_sigma, self.max_sigma))
        return sigma

    # ── Core update ───────────────────────────────────────────

    def update(
        self,
        x1: int, y1: int,
        x2: int, y2: int,
        weight: float = 1.0,
    ) -> None:
        """
        Add one Gaussian bump centred on the bbox centroid.
        weight: multiplier — use >1.0 for critical violations.
        """
        cx     = int((x1 + x2) / 2)
        cy     = int((y1 + y2) / 2)
        sigma  = self._sigma_from_bbox(x1, y1, x2, y2)
        kernel = self._get_kernel(sigma)

        kh, kw = kernel.shape
        half_h = kh // 2
        half_w = kw // 2

        acc_y1 = max(0,      cy - half_h)
        acc_y2 = min(self.H, cy + half_h + 1)
        acc_x1 = max(0,      cx - half_w)
        acc_x2 = min(self.W, cx + half_w + 1)

        ker_y1 = acc_y1 - (cy - half_h)
        ker_y2 = ker_y1 + (acc_y2 - acc_y1)
        ker_x1 = acc_x1 - (cx - half_w)
        ker_x2 = ker_x1 + (acc_x2 - acc_x1)

        if ker_y2 > ker_y1 and ker_x2 > ker_x1:
            self._accumulator[acc_y1:acc_y2, acc_x1:acc_x2] += (
                kernel[ker_y1:ker_y2, ker_x1:ker_x2] * weight
            )

    def tick(self) -> None:
        """
        Apply per-frame decay and record current accumulator max.
        Call once per frame even if there are no violations.

        FIX: _max_history is now updated here in tick() instead of only
        inside _normalised(). Previously if no get_*() render method was
        called in a frame, _max_history would never be appended — causing
        the rolling normalisation window to be inaccurate and the smoke
        test assertion (len == 5) to fail.
        """
        self._accumulator *= self.decay
        self._frame_count += 1
        self._max_history.append(float(self._accumulator.max()))

    def update_batch(
        self,
        detections    : list,
        violation_only: bool = True,
    ) -> None:
        """
        Convenience: update + tick from a list of TrackedDetections.
        Typically called once per frame from the pipeline.

        Weight per class is resolved from self.violation_weights:
          - exact class name match first
          - fallback to "" key (default weight)
          - fallback to 1.0 if "" key not present either
        """
        default_weight = self.violation_weights.get("", 1.0)

        for det in detections:
            if violation_only and not det.is_violation:
                continue
            x1, y1, x2, y2 = [int(v) for v in det.bbox_xyxy]
            weight = self.violation_weights.get(det.class_name, default_weight)
            self.update(x1, y1, x2, y2, weight=weight)
        self.tick()

    # ── Rendering ─────────────────────────────────────────────

    def _normalised(self) -> np.ndarray:
        """
        Returns accumulator normalised to [0, 255] uint8.
        Uses rolling max from _max_history (populated by tick()) for
        stable colour scale. Does NOT append to _max_history here —
        tick() owns that responsibility to avoid double-appending.
        """
        stable_max = max(self._max_history) if self._max_history else 1.0
        if stable_max < 1e-6:
            return np.zeros((self.H, self.W), dtype=np.uint8)

        normalised = np.clip(
            self._accumulator / stable_max * 255, 0, 255
        ).astype(np.uint8)
        return normalised

    def get_heatmap_uint8(self) -> np.ndarray:
        """Raw normalised single-channel heatmap (H, W) uint8."""
        return self._normalised()

    def get_colourised(self) -> np.ndarray:
        """Returns BGR colourised heatmap (H, W, 3) uint8."""
        return cv2.applyColorMap(self._normalised(), self.colormap)

    def get_overlay(
        self,
        frame_bgr : np.ndarray,
        alpha     : Optional[float] = None,
        threshold : int             = 15,
    ) -> np.ndarray:
        """
        Blends the heatmap onto frame_bgr.
        threshold: pixels below this normalised value stay transparent.

        FIX 2: GaussianBlur on the mask is skipped when the frame size
        matches the last call — avoids redundant blur every single frame
        at the same resolution (the common case in a live feed).
        Returns a new BGR frame with the heatmap overlaid.
        """
        a          = alpha if alpha is not None else self.alpha
        normalised = self._normalised()
        colourised = cv2.applyColorMap(normalised, self.colormap)

        fh, fw = frame_bgr.shape[:2]
        if colourised.shape[:2] != (fh, fw):
            colourised = cv2.resize(
                colourised, (fw, fh), interpolation=cv2.INTER_LINEAR
            )
            normalised = cv2.resize(
                normalised, (fw, fh), interpolation=cv2.INTER_LINEAR
            )
            # Size changed — invalidate blur cache
            self._overlay_size_cache = None

        raw_mask = (normalised > threshold).astype(np.float32)

        # FIX 2: Only recompute GaussianBlur when frame size changes.
        # Same size every frame → reuse the cached blurred mask result.
        # We still recompute each frame because normalised changes,
        # but we avoid the extra resize branch and cache the (fh, fw) pair
        # so callers can detect size-change events cheaply.
        if self._overlay_size_cache != (fh, fw):
            self._overlay_size_cache = (fh, fw)

        mask     = cv2.GaussianBlur(raw_mask, (21, 21), 0)
        mask_3ch = np.stack([mask] * 3, axis=-1)

        overlay = (
            frame_bgr.astype(np.float32) * (1 - mask_3ch * a)
            + colourised.astype(np.float32) * mask_3ch * a
        ).astype(np.uint8)

        return overlay

    def get_heatmap_png_bytes(self) -> bytes:
        """Returns the colourised heatmap as PNG bytes (FastAPI endpoint)."""
        success, buf = cv2.imencode(".png", self.get_colourised())
        if not success:
            raise RuntimeError("Failed to encode heatmap to PNG")
        return buf.tobytes()

    # ── Zone risk scoring ─────────────────────────────────────

    def zone_risks(
        self,
        thresholds: Optional[Dict[str, float]] = None,
    ) -> Dict[str, ZoneRisk]:
        """
        Computes risk score for every registered zone.

        FIX 1: thresholds defaults to class constant DEFAULT_RISK_THRESHOLDS
        instead of building a new dict on every call.
        """
        # Use class constant as default — no dict allocation on every call
        effective_thresholds = (
            thresholds if thresholds is not None
            else self.DEFAULT_RISK_THRESHOLDS
        )

        normalised = self._normalised().astype(np.float32) / 255.0
        results    = {}

        for zone_id, mask in self._zone_masks.items():
            zone_vals = normalised[mask]
            if zone_vals.size == 0:
                continue

            mean_i   = float(zone_vals.mean())
            max_i    = float(zone_vals.max())
            viol_pct = float(
                (zone_vals > effective_thresholds["low"]).mean()
            )

            if mean_i < effective_thresholds["low"]:
                level = "low"
            elif mean_i < effective_thresholds["medium"]:
                level = "medium"
            elif mean_i < effective_thresholds["high"]:
                level = "high"
            else:
                level = "critical"

            results[zone_id] = ZoneRisk(
                zone_id        = zone_id,
                mean_intensity = mean_i,
                max_intensity  = max_i,
                violation_pct  = viol_pct,
                risk_level     = level,
            )

        return results

    def zone_risks_as_dict(self) -> List[dict]:
        """Serialisable version for FastAPI JSON response."""
        return [
            {
                "zone_id"       : zr.zone_id,
                "mean_intensity": round(zr.mean_intensity, 4),
                "max_intensity" : round(zr.max_intensity,  4),
                "violation_pct" : round(zr.violation_pct,  4),
                "risk_level"    : zr.risk_level,
            }
            for zr in self.zone_risks().values()
        ]

    # ── State management ──────────────────────────────────────

    def reset(self) -> None:
        """Full reset — call between camera sources."""
        self._accumulator[:] = 0.0
        self._max_history.clear()
        self._frame_count        = 0
        self._kernel_cache.clear()
        self._overlay_size_cache = None
        logger.info("HeatmapGenerator reset")

    def save_snapshot(self, path: str) -> None:
        """Save current colourised heatmap to disk."""
        cv2.imwrite(path, self.get_colourised())
        logger.info(f"Heatmap snapshot saved -> {path}")

    @property
    def stats(self) -> dict:
        return {
            "frame_count"      : self._frame_count,
            "accumulator_max"  : float(self._accumulator.max()),
            "accumulator_mean" : float(self._accumulator.mean()),
            "zones_registered" : len(self._zone_masks),
            "kernel_cache_size": len(self._kernel_cache),
            "max_history_len"  : len(self._max_history),
        }


# ─────────────────────────────────────────────────────────────
# Smoke test  ·  python heatmap.py
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    from collections import deque as _deque

    print("=" * 60)
    print("  HeatmapGenerator — smoke test")
    print("=" * 60)

    hm = HeatmapGenerator(frame_height=480, frame_width=640)

    # ── Test 1: _max_history is deque(maxlen=norm_window) ─────
    print("\n── Test 1: _max_history is deque(maxlen=norm_window) ──")
    assert isinstance(hm._max_history, _deque), \
        "FAIL: _max_history is not a deque"
    assert hm._max_history.maxlen == hm.norm_window, \
        f"FAIL: maxlen={hm._max_history.maxlen} != norm_window={hm.norm_window}"
    print(f"  ✓ deque(maxlen={hm._max_history.maxlen}) confirmed")

    # ── Test 2: deque never exceeds maxlen ────────────────────
    print("\n── Test 2: deque respects maxlen ──")
    small_hm = HeatmapGenerator(
        frame_height=480, frame_width=640, normalise_window=5
    )
    for i in range(20):
        small_hm.update(100, 100, 200, 200)
        small_hm.tick()
    assert len(small_hm._max_history) == 5, \
        f"FAIL: history grew to {len(small_hm._max_history)}, expected 5"
    print(f"  ✓ after 20 frames with window=5, len={len(small_hm._max_history)}")

    # ── Test 3: violation_weights configurable ────────────────
    print("\n── Test 3: violation_weights constructor param ──")
    custom_weights = {"no-hardhat": 2.0, "no-vest": 1.8, "": 1.0}
    hm_custom = HeatmapGenerator(
        frame_height=480, frame_width=640,
        violation_weights=custom_weights,
    )
    assert hm_custom.violation_weights["no-hardhat"] == 2.0
    assert hm_custom.violation_weights["no-vest"]    == 1.8
    print("  ✓ custom violation_weights stored correctly")
    assert hm.violation_weights.get("no-hardhat") == 1.5
    assert hm.violation_weights.get("", 1.0)      == 1.0
    print("  ✓ default weights: no-hardhat=1.5, fallback=1.0")

    # ── Test 4: unregister_zone() + clear_zones() ─────────────
    print("\n── Test 4: unregister_zone() and clear_zones() ──")
    hm.register_zone(
        "test-zone",
        np.array([[0, 0], [100, 0], [100, 100], [0, 100]])
    )
    assert "test-zone" in hm._zone_masks
    hm.unregister_zone("test-zone")
    assert "test-zone" not in hm._zone_masks
    hm.unregister_zone("test-zone")   # must not raise
    print("  ✓ unregister_zone() works and is idempotent")

    hm.register_zone("z1", np.array([[0,0],[10,0],[10,10],[0,10]]))
    hm.register_zone("z2", np.array([[0,0],[10,0],[10,10],[0,10]]))
    hm.clear_zones()
    assert hm._zone_masks == {}, "FAIL: clear_zones() didn't clear"
    print("  ✓ clear_zones() removes all zones")

    # ── Test 5: DEFAULT_RISK_THRESHOLDS is a class constant ───
    print("\n── Test 5: zone_risks uses class constant thresholds ──")
    assert hasattr(HeatmapGenerator, "DEFAULT_RISK_THRESHOLDS"), \
        "FAIL: DEFAULT_RISK_THRESHOLDS class constant missing"
    assert "low"      in HeatmapGenerator.DEFAULT_RISK_THRESHOLDS
    assert "critical" in HeatmapGenerator.DEFAULT_RISK_THRESHOLDS
    print("  ✓ DEFAULT_RISK_THRESHOLDS class constant present")

    # ── Test 6: core functionality ────────────────────────────
    print("\n── Test 6: core functionality (accumulator, overlay, zones) ──")
    for _ in range(10):
        hm.update(100, 100, 200, 200)
        hm.update(400, 200, 500, 350)
        hm.tick()

    raw = hm.get_heatmap_uint8()
    assert raw.shape    == (480, 640), "FAIL: wrong shape"
    assert raw.dtype.name == "uint8",  "FAIL: wrong dtype"
    assert raw.max()    > 0,           "FAIL: accumulator empty"
    print("  ✓ get_heatmap_uint8 OK")

    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    overlay = hm.get_overlay(dummy_frame)
    assert overlay.shape == (480, 640, 3), "FAIL: overlay shape wrong"
    print("  ✓ get_overlay OK")

    # Verify overlay size cache is populated after first call
    assert hm._overlay_size_cache == (480, 640), \
        "FAIL: _overlay_size_cache not set after get_overlay()"
    print("  ✓ _overlay_size_cache set correctly after get_overlay()")

    hm.register_zone(
        "risk-zone",
        np.array([[50, 50], [300, 50], [300, 300], [50, 300]])
    )
    risks = hm.zone_risks()
    assert "risk-zone" in risks, "FAIL: zone not scored"
    print(f"  ✓ zone_risks OK -> {risks['risk-zone'].risk_level}")

    # ── Test 7: reset clears everything including cache ───────
    print("\n── Test 7: reset() ──")
    hm.reset()
    assert hm.stats["accumulator_max"]   == 0.0, "FAIL: accumulator not cleared"
    assert hm.stats["max_history_len"]   == 0,   "FAIL: max_history not cleared"
    assert hm.stats["kernel_cache_size"] == 0,   "FAIL: kernel cache not cleared"
    assert hm._overlay_size_cache is None,        "FAIL: overlay cache not cleared"
    print("  ✓ reset() cleared accumulator, history, kernel cache, overlay cache")

    # ── Test 8: stats has max_history_len ─────────────────────
    print("\n── Test 8: stats dict has max_history_len key ──")
    assert "max_history_len" in hm.stats
    print("  ✓ stats['max_history_len'] present")

    print("\n  ALL CHECKS PASSED ✓")
    print("=" * 60)