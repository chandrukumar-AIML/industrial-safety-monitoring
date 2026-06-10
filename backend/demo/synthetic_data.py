"""
backend/demo/synthetic_data.py

Demo Mode — generates realistic synthetic safety data for portfolio
showcase, client demos, and trade show presentations.

No real cameras needed. Generates:
  - Streaming violation events (random but realistic)
  - Simulated worker profiles with risk scores
  - Historical compliance trends
  - Fire / pose / proximity alerts
  - Weekly report summary

Enable via: DEMO_MODE=true in .env
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from loguru import logger

# ── Config ────────────────────────────────────────────────────
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"
DEMO_VIOLATION_RATE = float(os.getenv("DEMO_VIOLATION_RATE", "0.3"))  # violations per second
DEMO_WORKERS = int(os.getenv("DEMO_WORKERS", "12"))
DEMO_CAMERAS = int(os.getenv("DEMO_CAMERAS", "4"))

# ── Constants ─────────────────────────────────────────────────
_PPE_CLASSES = [
    "no helmet", "no gloves", "no goggles", "no boots",
    "no mask", "no vest", "helmet", "gloves", "goggles",
]
_VIOLATION_CLASSES = [c for c in _PPE_CLASSES if c.startswith("no")]
_ZONES = ["Zone-A (Welding)", "Zone-B (Chemical)", "Zone-C (Loading Dock)", "Zone-D (Assembly)"]
_ZONE_IDS = ["zone-a", "zone-b", "zone-c", "zone-d"]
_ZONE_TYPES = ["danger", "restricted", "danger", "safe"]
_WORKER_NAMES = [
    "Arjun Kumar", "Priya Sharma", "Ravi Patel", "Anitha Raj",
    "Karthik Nair", "Meena Devi", "Suresh Babu", "Lakshmi Rao",
    "Vikram Singh", "Deepa Menon", "Sanjay Gupta", "Pooja Iyer",
]
_DEPARTMENTS = ["Welding", "Chemical Handling", "Logistics", "Assembly", "Quality Control"]
_CAMERA_IDS = ["cam-01", "cam-02", "cam-03", "cam-04"]
_CAMERA_NAMES = ["Main Gate", "Welding Bay", "Chemical Store", "Loading Dock"]
_SEVERITY_LEVELS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


@dataclass
class DemoStats:
    """Running stats for the demo session."""
    total_violations: int = 0
    total_fire_alerts: int = 0
    total_pose_alerts: int = 0
    total_proximity_alerts: int = 0
    compliance_score: float = 87.3
    started_at: float = field(default_factory=time.monotonic)


_demo_stats = DemoStats()


# ── Synthetic data generators ─────────────────────────────────

def generate_violation_event(frame_idx: int = 0) -> Dict[str, Any]:
    """Generate one realistic PPE violation event."""
    track_id = random.randint(1, DEMO_WORKERS)
    zone_idx = random.randint(0, len(_ZONES) - 1)
    violation_class = random.choice(_VIOLATION_CLASSES)
    confidence = round(random.uniform(0.55, 0.98), 3)

    return {
        "id": random.randint(1000, 99999),
        "track_id": track_id,
        "class_name": violation_class,
        "confidence": confidence,
        "zone_id": _ZONE_IDS[zone_idx],
        "zone_name": _ZONES[zone_idx],
        "camera_id": random.choice(_CAMERA_IDS),
        "frame_idx": frame_idx,
        "bbox_x1": round(random.uniform(0.1, 0.4), 3),
        "bbox_y1": round(random.uniform(0.1, 0.4), 3),
        "bbox_x2": round(random.uniform(0.5, 0.9), 3),
        "bbox_y2": round(random.uniform(0.5, 0.9), 3),
        "severity": _get_severity(zone_idx, violation_class),
        "acknowledged": False,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "demo": True,
    }


def generate_worker_profiles() -> List[Dict[str, Any]]:
    """Generate synthetic worker profiles with realistic risk distribution."""
    profiles = []
    for i, name in enumerate(_WORKER_NAMES[:DEMO_WORKERS]):
        risk_score = round(random.triangular(0, 100, 20), 1)  # skewed low
        risk_level = _risk_level(risk_score)
        profiles.append({
            "worker_id": f"W{1000 + i}",
            "full_name": name,
            "department": random.choice(_DEPARTMENTS),
            "shift": random.choice(["morning", "afternoon", "night"]),
            "role": random.choice(["operator", "supervisor", "technician"]),
            "risk_score": risk_score,
            "risk_level": risk_level,
            "hr_alerted": risk_score > 75,
            "active": True,
            "enrolled": random.random() > 0.2,
            "photo_path": None,
            "created_at": (
                datetime.now(timezone.utc) - timedelta(days=random.randint(30, 365))
            ).isoformat(),
            "demo": True,
        })
    return sorted(profiles, key=lambda x: x["risk_score"], reverse=True)


def generate_zone_definitions() -> List[Dict[str, Any]]:
    """Generate synthetic zone definitions."""
    zones = []
    for i, (zone_id, zone_name, zone_type) in enumerate(
        zip(_ZONE_IDS, _ZONES, _ZONE_TYPES)
    ):
        # Generate a simple rectangular polygon
        x_start = 0.1 + i * 0.2
        y_start = 0.1
        zones.append({
            "id": i + 1,
            "zone_id": zone_id,
            "zone_name": zone_name,
            "zone_type": zone_type,
            "camera_id": _CAMERA_IDS[i % len(_CAMERA_IDS)],
            "polygon_norm": [
                [x_start, y_start],
                [x_start + 0.15, y_start],
                [x_start + 0.15, y_start + 0.6],
                [x_start, y_start + 0.6],
            ],
            "required_ppe": _zone_ppe(zone_type),
            "alert_enabled": True,
            "dwell_threshold_s": 2.0,
            "color_hex": "#ef4444" if zone_type == "danger" else "#f97316",
            "active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "demo": True,
        })
    return zones


def generate_camera_list() -> List[Dict[str, Any]]:
    """Generate synthetic camera list."""
    cameras = []
    for i, (cam_id, cam_name) in enumerate(zip(_CAMERA_IDS, _CAMERA_NAMES)):
        cameras.append({
            "camera_id": cam_id,
            "name": cam_name,
            "url": f"rtsp://demo:demo@192.168.1.{100+i}:554/stream",
            "status": "online" if random.random() > 0.1 else "offline",
            "fps": round(random.uniform(22, 30), 1),
            "resolution": "1920x1080",
            "location": _ZONES[i],
            "demo": True,
        })
    return cameras


def generate_dashboard_stats() -> Dict[str, Any]:
    """Generate realistic dashboard KPI stats."""
    now = datetime.now(timezone.utc)
    return {
        "violations_today": random.randint(3, 24),
        "violations_this_week": random.randint(15, 80),
        "compliance_score": round(_demo_stats.compliance_score, 1),
        "active_workers": DEMO_WORKERS,
        "high_risk_workers": random.randint(1, 3),
        "active_fire_alerts": 0,
        "active_cameras": DEMO_CAMERAS,
        "pipeline_fps": round(random.uniform(24, 29), 1),
        "model_version": "v2.3.1-demo",
        "uptime_hours": round((time.monotonic() - _demo_stats.started_at) / 3600, 2),
        "timestamp": now.isoformat(),
        "demo": True,
    }


def generate_violation_history(days: int = 30) -> List[Dict[str, Any]]:
    """Generate 30-day violation history for analytics charts."""
    history = []
    now = datetime.now(timezone.utc)
    for day in range(days, 0, -1):
        date = now - timedelta(days=day)
        # Realistic pattern: more violations mid-week, fewer on weekends
        weekday_factor = 1.0 if date.weekday() < 5 else 0.4
        base = random.randint(2, 15)
        history.append({
            "date": date.date().isoformat(),
            "violations": int(base * weekday_factor),
            "compliance_score": round(random.uniform(75, 95), 1),
            "high_risk": random.randint(0, 3),
            "fire_alerts": 1 if random.random() < 0.05 else 0,
            "demo": True,
        })
    return history


def generate_compliance_by_class() -> Dict[str, int]:
    """Generate violation counts by PPE class."""
    return {
        "no helmet": random.randint(5, 25),
        "no gloves": random.randint(3, 18),
        "no goggles": random.randint(2, 12),
        "no boots": random.randint(1, 8),
        "no mask": random.randint(4, 20),
        "no vest": random.randint(3, 15),
    }


def generate_weekly_report_summary() -> Dict[str, Any]:
    """Generate demo weekly report data."""
    now = datetime.now(timezone.utc)
    week_start = now - timedelta(days=7)
    return {
        "id": 42,
        "report_date": now.date().isoformat(),
        "week_start": week_start.date().isoformat(),
        "week_end": now.date().isoformat(),
        "site_score": round(random.uniform(78, 94), 1),
        "prev_week_score": round(random.uniform(75, 92), 1),
        "score_delta": round(random.uniform(-5, 8), 1),
        "total_violations": random.randint(18, 65),
        "total_workers": DEMO_WORKERS,
        "high_risk_count": random.randint(1, 4),
        "violations_by_class": generate_compliance_by_class(),
        "violations_by_zone": {z: random.randint(1, 15) for z in _ZONE_IDS},
        "incident_summary": (
            "This week showed improved compliance in Zone-A with a 12% reduction in helmet "
            "violations following last week's safety briefing. Zone-B chemical handling continues "
            "to require attention — 3 workers were flagged for repeated glove violations. "
            "Recommend immediate targeted training for the chemical handling department."
        ),
        "pdf_path": None,
        "email_sent": False,
        "created_at": now.isoformat(),
        "has_pdf": False,
        "demo": True,
    }


def generate_fire_alert() -> Dict[str, Any]:
    """Generate a demo fire/smoke detection event."""
    return {
        "id": random.randint(1000, 9999),
        "hazard_type": random.choice(["fire", "smoke"]),
        "confidence": round(random.uniform(0.72, 0.96), 3),
        "bbox_x1": 0.3, "bbox_y1": 0.2, "bbox_x2": 0.7, "bbox_y2": 0.8,
        "zone_id": "zone-b",
        "frame_idx": random.randint(1000, 9999),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "acknowledged": False,
        "demo": True,
    }


def generate_pose_hazards() -> List[Dict[str, Any]]:
    """Generate demo pose hazard events."""
    hazards = []
    for _ in range(random.randint(1, 4)):
        hazards.append({
            "id": random.randint(100, 999),
            "track_id": random.randint(1, DEMO_WORKERS),
            "hazard_type": random.choice(["dangerous_bending", "fatigue", "fall_risk", "reaching"]),
            "severity": random.choice(["HIGH", "CRITICAL"]),
            "confidence": round(random.uniform(0.65, 0.95), 3),
            "zone_id": random.choice(_ZONE_IDS),
            "frame_idx": random.randint(1000, 9999),
            "landmark_data": {},
            "combined_alert": random.random() > 0.7,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "demo": True,
        })
    return hazards


# ── Async demo stream generator ───────────────────────────────

async def demo_violation_stream(callback, stop_event: asyncio.Event):
    """
    Continuously generates demo violations and calls callback.
    Use this to feed the WebSocket stream in demo mode.
    """
    frame_idx = 0
    logger.info("Demo violation stream started")
    while not stop_event.is_set():
        if random.random() < DEMO_VIOLATION_RATE:
            event = generate_violation_event(frame_idx)
            _demo_stats.total_violations += 1
            _demo_stats.compliance_score = max(60, _demo_stats.compliance_score - 0.01)
            try:
                await callback(event)
            except Exception as exc:
                logger.debug("Demo stream callback error: {}", exc)
        frame_idx += 1
        await asyncio.sleep(1.0 / 10)  # 10 Hz synthetic frame rate


# ── Helpers ──────────────────────────────────────────────────

def _get_severity(zone_idx: int, violation_class: str) -> str:
    zone_type = _ZONE_TYPES[zone_idx]
    if zone_type == "danger":
        return "CRITICAL" if "helmet" in violation_class else "HIGH"
    if zone_type == "restricted":
        return "HIGH"
    return random.choice(["LOW", "MEDIUM"])


def _risk_level(score: float) -> str:
    if score >= 75: return "CRITICAL"
    if score >= 50: return "HIGH"
    if score >= 25: return "MEDIUM"
    return "LOW"


def _zone_ppe(zone_type: str) -> List[str]:
    if zone_type == "danger":
        return ["helmet", "gloves", "goggles", "boots", "mask"]
    if zone_type == "restricted":
        return ["helmet", "gloves", "vest"]
    return ["helmet", "vest"]


def is_demo_mode() -> bool:
    """Check if demo mode is active."""
    return DEMO_MODE
