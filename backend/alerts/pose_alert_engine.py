"""
alerts/pose_alert_engine.py

Classifies pose hazards from MediaPipe landmarks.

# FIXED: Move imports to module level (no runtime import inside methods)
# FIXED: Configurable thresholds via env vars with validation
# IMPROVED: Spatial indexing hint for O(n²) proximity optimization
# IMPROVED: Type hints for PoseLandmarks dependency
# FIXED: Temporal history cleanup to prevent memory leaks
"""

from __future__ import annotations

import math
import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

import cv2
import numpy as np
from loguru import logger
from enum import Enum
from pydantic import BaseModel, Field  # FIXED: removed stale v1 validator import

# ── Type hint only import (no runtime cost) ───────────────────
if TYPE_CHECKING:
    from inference.pose_detector import PoseLandmarks


# ── Config: Load from env with validation ─────────────────────
# FIXED: module-level raise → warning + clamp (raise at import crashes the app)
def _cfg(name: str, raw: str, default: float, lo: float, hi: float) -> float:
    try:
        val = float(raw)
    except ValueError:
        val = default
    if not lo <= val <= hi:
        logger.warning("{} out of {}-{}: {} — clamping to {}", name, lo, hi, val, default)
        return default
    return val

_BENDING_ANGLE_THRESHOLD = _cfg("POSE_BENDING_ANGLE_THRESHOLD",
    os.getenv("POSE_BENDING_ANGLE_THRESHOLD", "50.0"), 50.0, 0.0, 90.0)

_HEAD_DROP_THRESHOLD = _cfg("POSE_HEAD_DROP_THRESHOLD",
    os.getenv("POSE_HEAD_DROP_THRESHOLD", "40.0"), 40.0, 0.0, 90.0)

_FATIGUE_PERSISTENCE_S = _cfg("POSE_FATIGUE_PERSISTENCE_SECONDS",
    os.getenv("POSE_FATIGUE_PERSISTENCE_SECONDS", "3.0"), 3.0, 0.5, 10.0)

_FALL_VELOCITY_THRESHOLD = _cfg("POSE_FALL_VELOCITY_THRESHOLD",
    os.getenv("POSE_FALL_VELOCITY_THRESHOLD", "0.15"), 0.15, 0.05, 0.5)

_FALL_HISTORY_S = float(os.getenv("POSE_FALL_HISTORY_SECONDS", "0.5"))
_FALL_COOLDOWN_S = float(os.getenv("POSE_FALL_COOLDOWN_SECONDS", "10.0"))


# ── Hazard types enum ────────────────────────────────────────
class HazardType(str, Enum):
    DANGEROUS_BENDING = "dangerous_bending"
    REACHING_RESTRICTED = "reaching_restricted_area"
    FATIGUE_POSTURE = "fatigue_posture"
    FALL_DETECTED = "fall_detected"


# ── Pydantic model for PoseHazard output ─────────────────────
@dataclass
class PoseHazard:
    """One detected pose hazard event."""
    hazard_type: str
    severity: str  # CRITICAL | HIGH | MEDIUM | LOW
    confidence: float  # [0, 1]
    track_id: int
    zone_id: Optional[str]
    frame_idx: int
    landmark_data: dict  # relevant landmarks for audit
    description: str  # human-readable explanation
    combined_alert: bool = False  # True if also has PPE violation
    
    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization."""
        return {
            "hazard_type": self.hazard_type,
            "severity": self.severity,
            "confidence": self.confidence,
            "track_id": self.track_id,
            "zone_id": self.zone_id,
            "frame_idx": self.frame_idx,
            "landmark_data": self.landmark_data,
            "description": self.description,
            "combined_alert": self.combined_alert,
        }


# ── Detector 1: DangerousBendingDetector ─────────────────────
class DangerousBendingDetector:
    """
    Detects dangerous forward bending near machinery.
    
    Method: compute angle at hip between shoulder and knee.
    Normal standing: ~160-170°
    Dangerous bending: < threshold
    """

    def detect(
        self,
        pose: "PoseLandmarks",
        track_id: int,
        frame_idx: int,
    ) -> Optional[PoseHazard]:
        # Use left side — fall back to right if left not visible
        angle = pose.angle_between("left_shoulder", "left_hip", "left_knee")
        side = "left"
        if angle is None:
            angle = pose.angle_between("right_shoulder", "right_hip", "right_knee")
            side = "right"
        if angle is None:
            return None

        if angle > _BENDING_ANGLE_THRESHOLD:
            return None

        confidence = max(0.0, min(1.0,
            (_BENDING_ANGLE_THRESHOLD - angle) / _BENDING_ANGLE_THRESHOLD
        ))

        hip = pose.get(f"{side}_hip")
        knee = pose.get(f"{side}_knee")
        shoul = pose.get(f"{side}_shoulder")

        return PoseHazard(
            hazard_type=HazardType.DANGEROUS_BENDING.value,
            severity="HIGH",
            confidence=round(confidence, 3),
            track_id=track_id,
            zone_id=None,
            frame_idx=frame_idx,
            landmark_data={
                "bend_angle": round(angle, 1),
                "threshold": _BENDING_ANGLE_THRESHOLD,
                "side": side,
                "hip": [round(hip[0], 3), round(hip[1], 3)] if hip else None,
            },
            description=(
                f"Worker bending at {angle:.0f}° — "
                f"dangerous posture near machinery "
                f"(threshold: {_BENDING_ANGLE_THRESHOLD}°)"
            ),
        )


# ── Detector 2: ReachingDetector ─────────────────────────────
class ReachingDetector:
    """
    Detects wrist reaching into registered danger/restricted zones.
    
    # IMPROVED: Spatial indexing hint for large zone lists
    """

    def __init__(self, zone_polygons: Dict[str, list] = None) -> None:
        self._zone_polygons = zone_polygons or {}
        # Optional: build spatial index for large zone lists
        self._spatial_index: Optional[Dict] = None
        if len(self._zone_polygons) > 10:
            self._build_spatial_index()

    def _build_spatial_index(self) -> None:
        """Build simple grid index for faster zone lookup."""
        # Future: Use R-tree or quadtree for O(log n) lookup
        self._spatial_index = {
            zone_id: {
                "bbox": self._compute_bbox(polygon),
                "polygon": polygon,
            }
            for zone_id, polygon in self._zone_polygons.items()
        }

    def _compute_bbox(self, polygon_norm: List[List[float]]) -> Tuple[float, float, float, float]:
        """Compute bounding box for normalized polygon."""
        xs = [p[0] for p in polygon_norm]
        ys = [p[1] for p in polygon_norm]
        return min(xs), min(ys), max(xs), max(ys)

    def update_zones(self, zone_polygons: Dict[str, list]) -> None:
        """Update registered zones. Called when zones change."""
        self._zone_polygons = zone_polygons
        if len(zone_polygons) > 10:
            self._build_spatial_index()
        else:
            self._spatial_index = None

    def detect(
        self,
        pose: "PoseLandmarks",
        track_id: int,
        frame_idx: int,
        frame_wh: Tuple[int, int] = (640, 640),
    ) -> Optional[PoseHazard]:
        if not self._zone_polygons:
            return None

        fw, fh = frame_wh

        for side in ("left_wrist", "right_wrist"):
            wrist = pose.get(side)
            if wrist is None:
                continue

            # Convert normalised → pixel for polygon test
            wx_px = wrist[0] * fw
            wy_px = wrist[1] * fh

            for zone_id, polygon_norm in self._zone_polygons.items():
                # Optional: quick bbox reject before polygon test
                if self._spatial_index:
                    bbox = self._spatial_index[zone_id]["bbox"]
                    if not (bbox[0] <= wrist[0] <= bbox[2] and bbox[1] <= wrist[1] <= bbox[3]):
                        continue
                
                poly_px = np.array(
                    [[int(p[0] * fw), int(p[1] * fh)] for p in polygon_norm],
                    dtype=np.float32,
                )
                dist = cv2.pointPolygonTest(poly_px, (wx_px, wy_px), False)
                if dist >= 0:
                    return PoseHazard(
                        hazard_type=HazardType.REACHING_RESTRICTED.value,
                        severity="CRITICAL",
                        confidence=min(1.0, wrist[2]),
                        track_id=track_id,
                        zone_id=zone_id,
                        frame_idx=frame_idx,
                        landmark_data={
                            "wrist": side,
                            "wrist_x": round(wrist[0], 3),
                            "wrist_y": round(wrist[1], 3),
                            "zone_id": zone_id,
                        },
                        description=(
                            f"Worker's {side.replace('_', ' ')} "
                            f"detected inside restricted zone '{zone_id}'"
                        ),
                    )
        return None


# ── Detector 3: FatigueDetector ──────────────────────────────
class FatigueDetector:
    """
    Detects fatigue posture — sustained head drooping.
    
    # FIXED: Temporal history cleanup to prevent memory leaks
    """

    def __init__(self, max_history_s: float = 10.0) -> None:
        # track_id → deque of (timestamp, head_angle)
        self._history: Dict[int, deque] = defaultdict(
            lambda: deque(maxlen=int(max_history_s * 30))  # 30fps assumption
        )
        self._max_history_s = max_history_s

    def _cleanup_old_entries(self, track_id: int, now: float) -> None:
        """Remove entries older than max_history_s."""
        history = self._history[track_id]
        while history and now - history[0][0] > self._max_history_s:
            history.popleft()

    def detect(
        self,
        pose: "PoseLandmarks",
        track_id: int,
        frame_idx: int,
    ) -> Optional[PoseHazard]:
        nose = pose.get("nose")
        shoulder_mid = pose.midpoint("left_shoulder", "right_shoulder")
        hip_mid = pose.midpoint("left_hip", "right_hip")

        if nose is None or shoulder_mid is None or hip_mid is None:
            return None

        # Approximate angle: nose → shoulder → hip
        v_head = (nose[0] - shoulder_mid[0], nose[1] - shoulder_mid[1])
        v_body = (hip_mid[0] - shoulder_mid[0], hip_mid[1] - shoulder_mid[1])

        dot = v_head[0]*v_body[0] + v_head[1]*v_body[1]
        mag = (
            (v_head[0]**2 + v_head[1]**2)**0.5 *
            (v_body[0]**2 + v_body[1]**2)**0.5
        )
        if mag < 1e-6:
            return None

        head_angle = math.degrees(math.acos(max(-1.0, min(1.0, dot / mag))))

        # Record in history
        now = time.monotonic()
        self._cleanup_old_entries(track_id, now)
        self._history[track_id].append((now, head_angle))

        # Check temporal persistence
        history = list(self._history[track_id])
        if len(history) < 3:
            return None

        # How long has head been drooping?
        drooping_since = None
        for ts, angle in history:
            if angle < _HEAD_DROP_THRESHOLD:
                if drooping_since is None:
                    drooping_since = ts
            else:
                drooping_since = None

        if drooping_since is None:
            return None

        duration = now - drooping_since
        if duration < _FATIGUE_PERSISTENCE_S:
            return None

        confidence = min(1.0, duration / (_FATIGUE_PERSISTENCE_S * 2))

        return PoseHazard(
            hazard_type=HazardType.FATIGUE_POSTURE.value,
            severity="MEDIUM",
            confidence=round(confidence, 3),
            track_id=track_id,
            zone_id=None,
            frame_idx=frame_idx,
            landmark_data={
                "head_angle": round(head_angle, 1),
                "drooping_duration": round(duration, 1),
                "threshold_angle": _HEAD_DROP_THRESHOLD,
            },
            description=(
                f"Worker showing fatigue posture for {duration:.1f}s — "
                f"head angle {head_angle:.0f}° "
                f"(threshold: {_HEAD_DROP_THRESHOLD}°)"
            ),
        )


# ── Detector 4: FallDetector ─────────────────────────────────
class FallDetector:
    """
    Detects worker falls via rapid downward hip displacement.
    
    # FIXED: Cooldown management + memory cleanup
    """

    def __init__(self) -> None:
        # track_id → deque of (timestamp, hip_y_normalised)
        self._hip_history: Dict[int, deque] = defaultdict(
            lambda: deque(maxlen=int(_FALL_HISTORY_S * 30 + 10))
        )
        # Suppress duplicate fall alerts
        self._fall_reported: Dict[int, float] = {}
        self._fall_cooldown_s = _FALL_COOLDOWN_S

    def _cleanup_old_entries(self, track_id: int, now: float) -> None:
        """Remove entries older than _FALL_HISTORY_S."""
        history = self._hip_history[track_id]
        while history and now - history[0][0] > _FALL_HISTORY_S:
            history.popleft()
        
        # Cleanup old fall reports
        self._fall_reported = {
            tid: ts for tid, ts in self._fall_reported.items()
            if now - ts < self._fall_cooldown_s * 2
        }

    def detect(
        self,
        pose: "PoseLandmarks",
        track_id: int,
        frame_idx: int,
    ) -> Optional[PoseHazard]:
        # Fall suppression cooldown
        now = time.monotonic()
        last_fall = self._fall_reported.get(track_id, 0)
        if now - last_fall < self._fall_cooldown_s:
            return None

        hip_mid = pose.midpoint("left_hip", "right_hip")
        if hip_mid is None:
            return None

        hip_y = hip_mid[1]  # normalised [0, 1], increases downward
        self._cleanup_old_entries(track_id, now)
        self._hip_history[track_id].append((now, hip_y))

        history = list(self._hip_history[track_id])
        if len(history) < 5:
            return None

        # Look at displacement over last _FALL_HISTORY_S seconds
        window = [(ts, y) for ts, y in history if now - ts <= _FALL_HISTORY_S]
        if len(window) < 3:
            return None

        earliest_y = window[0][1]
        latest_y = window[-1][1]
        elapsed = window[-1][0] - window[0][0]

        if elapsed < 1e-6:
            return None

        velocity = (latest_y - earliest_y) / elapsed  # positive = moving down

        if velocity < _FALL_VELOCITY_THRESHOLD:
            return None

        # Confirm: after fall, person should be low in frame
        if latest_y < 0.5:
            return None  # hip still high — not a fall

        self._fall_reported[track_id] = now
        confidence = min(1.0, velocity / (_FALL_VELOCITY_THRESHOLD * 2))

        return PoseHazard(
            hazard_type=HazardType.FALL_DETECTED.value,
            severity="CRITICAL",
            confidence=round(confidence, 3),
            track_id=track_id,
            zone_id=None,
            frame_idx=frame_idx,
            landmark_data={
                "hip_y_start": round(earliest_y, 3),
                "hip_y_end": round(latest_y, 3),
                "velocity_norm_ps": round(velocity, 3),
                "window_s": round(elapsed, 2),
            },
            description=(
                f"FALL DETECTED — Worker hip dropped "
                f"{(latest_y - earliest_y):.2%} of frame height "
                f"in {elapsed:.2f}s (velocity: {velocity:.2f}/s)"
            ),
        )


# ── Orchestrator: PoseAlertEngine ────────────────────────────
class PoseAlertEngine:
    """
    Orchestrates all four pose hazard detectors.
    
    # IMPROVED: Dependency injection for testability
    # IMPROVED: Combined alert logic with PPE violation correlation
    """

    def __init__(
        self,
        bending_detector: Optional[DangerousBendingDetector] = None,
        reaching_detector: Optional[ReachingDetector] = None,
        fatigue_detector: Optional[FatigueDetector] = None,
        fall_detector: Optional[FallDetector] = None,
    ) -> None:
        self._bending = bending_detector or DangerousBendingDetector()
        self._reaching = reaching_detector or ReachingDetector()
        self._fatigue = fatigue_detector or FatigueDetector()
        self._fall = fall_detector or FallDetector()

        logger.info("PoseAlertEngine initialised")

    def update_zones(self, zone_polygons: Dict[str, list]) -> None:
        """Pass current zone definitions to the reaching detector."""
        self._reaching.update_zones(zone_polygons)

    def evaluate(
        self,
        poses: list,  # List[PoseLandmarks]
        ppe_violations: list,  # List[TrackedDetection] with is_violation=True
        frame_wh: tuple,
        frame_idx: int = 0,
    ) -> List[PoseHazard]:
        """
        Run all hazard detectors on detected poses.
        Marks hazards as combined_alert if the same track also has a PPE violation.
        """
        if not poses:
            return []

        # Track IDs with active PPE violations for combined alert logic
        violating_tracks = {v.track_id for v in ppe_violations}

        all_hazards: List[PoseHazard] = []

        for i, pose in enumerate(poses):
            track_id = i  # simplified mapping — replace with proper track association in Phase J

            detectors = [
                self._bending.detect(pose, track_id, frame_idx),
                self._reaching.detect(pose, track_id, frame_idx, frame_wh),
                self._fatigue.detect(pose, track_id, frame_idx),
                self._fall.detect(pose, track_id, frame_idx),
            ]

            for hazard in detectors:
                if hazard is None:
                    continue

                # Mark as combined alert if also has PPE violation
                hazard.combined_alert = track_id in violating_tracks

                # Escalate to CRITICAL if combined
                if hazard.combined_alert and hazard.severity != "CRITICAL":
                    hazard.severity = "CRITICAL"
                    hazard.description += " [COMBINED: PPE violation + hazardous pose]"

                all_hazards.append(hazard)
                logger.warning(
                    "POSE HAZARD | type={} | severity={} | track={} | combined={}",
                    hazard.hazard_type, hazard.severity,
                    track_id, hazard.combined_alert,
                )

        return all_hazards

    def get_hazard_summary(self, hazards: List[PoseHazard]) -> dict:
        """Summary dict for WebSocket broadcast."""
        return {
            "total": len(hazards),
            "critical": sum(1 for h in hazards if h.severity == "CRITICAL"),
            "types": list({h.hazard_type for h in hazards}),
            "combined": sum(1 for h in hazards if h.combined_alert),
        }


# ── Singleton with lazy initialization ───────────────────────
_pose_alert_engine_instance: Optional[PoseAlertEngine] = None


def get_pose_alert_engine(**kwargs) -> PoseAlertEngine:
    """Get or create the pose alert engine singleton."""
    global _pose_alert_engine_instance
    if _pose_alert_engine_instance is None:
        _pose_alert_engine_instance = PoseAlertEngine(**kwargs)
    return _pose_alert_engine_instance


# Backward compatibility alias
pose_alert_engine = get_pose_alert_engine()