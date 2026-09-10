"""
backend/models.py

Pydantic v2 schemas — canonical data shapes for every
API request and response in the Industrial Safety Monitor API.

# FIXED: Consistent field naming (snake_case)
# FIXED: Proper enum values matching model output
# FIXED: Validation constraints on all fields
# IMPROVED: Clear OpenAPI examples and descriptions
# FIXED: No PII in schema examples
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlmodel import Field as SQLField
from sqlmodel import SQLModel

# ── Validation constants ──────────────────────────────────────
_MAX_CLASS_NAME_LEN: int = 64
_MAX_ZONE_ID_LEN: int = 64
_MAX_NOTES_LEN: int = 1000
_MIN_CONFIDENCE: float = 0.0
_MAX_CONFIDENCE: float = 1.0
_MIN_COORD: float = 0.0
_MAX_COORD: float = 4096  # Max reasonable frame dimension


# ── Enums ─────────────────────────────────────────────────────


class RiskLevel(str, Enum):
    """Worker risk assessment levels."""

    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class ViolationClass(str, Enum):
    """
    PPE violation classes detected by the YOLOv8 model.

    FIXED: All values use space-separated format to match actual
    model output labels (not hyphens).
    """

    no_helmet = "no helmet"
    no_vest = "no vest"
    no_hardhat = "no hardhat"
    no_gloves = "no gloves"
    no_goggles = "no goggles"
    no_boots = "no boots"
    no_mask = "no mask"
    no_suit = "no suit"


class AlertLevel(str, Enum):
    """Alert severity levels for notifications."""

    low = "LOW"
    medium = "MEDIUM"
    high = "HIGH"
    critical = "CRITICAL"


# ── Shared error envelope ─────────────────────────────────────


class ErrorDetail(BaseModel):
    """Single error detail item."""

    field: str | None = Field(
        default=None,
        description="Field that caused the error, if applicable",
    )
    message: str = Field(description="Human-readable error description")


class ErrorResponse(BaseModel):
    """
    Standard error envelope returned on all 4xx and 5xx responses.

    Example:
        {
          "error": "validation_error",
          "detail": [{"field": "confidence", "message": "must be in [0,1]"}]
        }
    """

    error: str = Field(description="Machine-readable error code")
    detail: list[ErrorDetail] = Field(description="List of error details")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error": "not_found",
                "detail": [{"message": "Violation not found"}],
            }
        }
    )


# ── SQLModel tables ───────────────────────────────────────────


class ViolationEvent(SQLModel, table=True):
    """Persisted violation record — one row per detected violation."""

    __tablename__ = "violation_events"

    id: int | None = SQLField(default=None, primary_key=True)
    track_id: int = SQLField(index=True, ge=0)
    class_name: str = SQLField(
        max_length=_MAX_CLASS_NAME_LEN,
        index=True,
    )
    confidence: float = SQLField(ge=_MIN_CONFIDENCE, le=_MAX_CONFIDENCE)
    zone_id: str | None = SQLField(
        default=None,
        max_length=_MAX_ZONE_ID_LEN,
    )
    bbox_x1: float = SQLField(ge=_MIN_COORD, le=_MAX_COORD)
    bbox_y1: float = SQLField(ge=_MIN_COORD, le=_MAX_COORD)
    bbox_x2: float = SQLField(ge=_MIN_COORD, le=_MAX_COORD)
    bbox_y2: float = SQLField(ge=_MIN_COORD, le=_MAX_COORD)
    frame_idx: int = SQLField(ge=0)
    camera_id: str | None = SQLField(default=None, max_length=64)
    site_id: str | None = SQLField(default=None, max_length=50)
    severity_level: str | None = SQLField(default=None, max_length=20)
    timestamp: datetime = SQLField(
        default_factory=lambda: datetime.now(UTC),
        index=True,
    )
    acknowledged: bool = SQLField(default=False)
    notes: str | None = SQLField(
        default=None,
        max_length=_MAX_NOTES_LEN,
    )

    @model_validator(mode="after")
    def validate_bbox_order(self) -> ViolationEvent:
        """Ensure bbox coordinates are in correct order (x1<x2, y1<y2)."""
        if self.bbox_x1 >= self.bbox_x2 or self.bbox_y1 >= self.bbox_y2:
            raise ValueError("bbox coordinates must satisfy x1<x2 and y1<y2")
        return self


class ZoneRiskRecord(SQLModel, table=True):
    """Periodic zone risk snapshot — written every 30 frames."""

    __tablename__ = "zone_risk_records"

    id: int | None = SQLField(default=None, primary_key=True)
    zone_id: str = SQLField(
        max_length=_MAX_ZONE_ID_LEN,
        index=True,
    )
    mean_intensity: float = SQLField(ge=0.0, le=1.0)
    max_intensity: float = SQLField(ge=0.0, le=1.0)
    violation_pct: float = SQLField(ge=0.0, le=1.0)
    risk_level: str = SQLField(max_length=20)
    timestamp: datetime = SQLField(
        default_factory=lambda: datetime.now(UTC),
        index=True,
    )


# ── New feature tables ────────────────────────────────────────


class Webhook(SQLModel, table=True):
    """Outbound webhook registration."""

    __tablename__ = "webhooks"

    id: int | None = SQLField(default=None, primary_key=True)
    name: str = SQLField(max_length=100, index=True)
    url: str = SQLField(max_length=500)
    webhook_type: str = SQLField(max_length=20, default="custom")
    events: str = SQLField(default="[]")  # JSON array
    secret: str | None = SQLField(default=None, max_length=200)
    active: bool = SQLField(default=True)
    created_at: datetime | None = SQLField(
        default=None,
        sa_column_kwargs={"server_default": "CURRENT_TIMESTAMP"},
    )


class Site(SQLModel, table=True):
    """Physical site / location."""

    __tablename__ = "sites"

    id: int | None = SQLField(default=None, primary_key=True)
    site_id: str = SQLField(max_length=50, unique=True, index=True)
    site_name: str = SQLField(max_length=100)
    location: str | None = SQLField(default=None, max_length=200)
    country: str | None = SQLField(default=None, max_length=50)
    timezone: str = SQLField(default="UTC", max_length=50)
    industry_type: str | None = SQLField(default=None, max_length=50)
    contact_email: str | None = SQLField(default=None, max_length=200)
    active: bool = SQLField(default=True)
    created_at: datetime | None = SQLField(
        default=None,
        sa_column_kwargs={"server_default": "CURRENT_TIMESTAMP"},
    )


class Shift(SQLModel, table=True):
    """Shift schedule template."""

    __tablename__ = "shifts"

    id: int | None = SQLField(default=None, primary_key=True)
    shift_name: str = SQLField(max_length=100)
    shift_type: str = SQLField(max_length=20, default="custom")
    start_time: str = SQLField(max_length=5)  # HH:MM
    end_time: str = SQLField(max_length=5)  # HH:MM
    site_id: str | None = SQLField(default=None, max_length=50)
    supervisor_name: str | None = SQLField(default=None, max_length=100)
    max_workers: int = SQLField(default=50)
    active: bool = SQLField(default=True)
    created_at: datetime | None = SQLField(
        default=None,
        sa_column_kwargs={"server_default": "CURRENT_TIMESTAMP"},
    )


class ShiftAssignment(SQLModel, table=True):
    """Worker ↔ Shift assignment."""

    __tablename__ = "shift_assignments"

    id: int | None = SQLField(default=None, primary_key=True)
    shift_id: int = SQLField(index=True)
    worker_id: str = SQLField(max_length=100, index=True)
    assigned_at: datetime | None = SQLField(
        default=None,
        sa_column_kwargs={"server_default": "CURRENT_TIMESTAMP"},
    )


class AuditLog(SQLModel, table=True):
    """Immutable audit trail — every significant action recorded here."""

    __tablename__ = "audit_log"

    id: int | None = SQLField(default=None, primary_key=True)
    action: str = SQLField(max_length=100, index=True)
    actor: str = SQLField(max_length=100, default="system", index=True)
    resource_type: str | None = SQLField(default=None, max_length=50)
    resource_id: str | None = SQLField(default=None, max_length=100)
    details: str | None = SQLField(default=None)  # JSON string
    ip_address: str | None = SQLField(default=None, max_length=45)
    created_at: datetime | None = SQLField(
        default=None,
        sa_column_kwargs={"server_default": "CURRENT_TIMESTAMP"},
        index=True,
    )


class ApiKey(SQLModel, table=True):
    """API key registration (hashed, never plaintext)."""

    __tablename__ = "api_keys"

    id: int | None = SQLField(default=None, primary_key=True)
    name: str = SQLField(max_length=100, index=True)
    role: str = SQLField(max_length=20, default="viewer")
    description: str | None = SQLField(default=None, max_length=500)
    key_hash: str = SQLField(max_length=64, unique=True)  # SHA-256 hex
    expires_at: datetime | None = SQLField(default=None)
    active: bool = SQLField(default=True)
    created_at: datetime | None = SQLField(
        default=None,
        sa_column_kwargs={"server_default": "CURRENT_TIMESTAMP"},
    )


# ── Multi-tenant ─────────────────────────────────────────────


class Organization(SQLModel, table=True):
    """
    Top-level tenant — one row per client company.
    All other tables carry org_id for row-level isolation.
    """

    __tablename__ = "organizations"

    id: int | None = SQLField(default=None, primary_key=True)
    org_id: str = SQLField(max_length=64, unique=True, index=True)
    org_name: str = SQLField(max_length=200)
    industry_type: str | None = SQLField(default=None, max_length=50)
    country: str = SQLField(default="IN", max_length=2)
    # Subscription
    plan: str = SQLField(default="starter", max_length=20)  # starter|growth|enterprise
    plan_status: str = SQLField(default="trial", max_length=20)  # trial|active|suspended|cancelled
    trial_ends_at: datetime | None = SQLField(default=None)
    # Limits
    max_cameras: int = SQLField(default=5)
    max_sites: int = SQLField(default=1)
    max_users: int = SQLField(default=10)
    # Razorpay
    razorpay_customer_id: str | None = SQLField(default=None, max_length=100)
    razorpay_subscription_id: str | None = SQLField(default=None, max_length=100)
    # Contact
    admin_email: str | None = SQLField(default=None, max_length=200)
    active: bool = SQLField(default=True)
    created_at: datetime | None = SQLField(
        default=None,
        sa_column_kwargs={"server_default": "CURRENT_TIMESTAMP"},
    )


# ── Industry PPE Profiles ─────────────────────────────────────


class IndustryPPEProfile(SQLModel, table=True):
    """
    Required PPE per industry per zone type.
    Seeded once; drives compliance checks.
    """

    __tablename__ = "industry_ppe_profiles"

    id: int | None = SQLField(default=None, primary_key=True)
    industry_type: str = SQLField(max_length=50, index=True)
    zone_type: str = SQLField(max_length=50, index=True)
    required_ppe: str = SQLField(default="[]")  # JSON list of class names
    risk_level: str = SQLField(default="HIGH", max_length=16)
    compliance_standard: str = SQLField(default="OSHA 1910.132", max_length=100)
    notes: str | None = SQLField(default=None, max_length=500)


# ── Alert Escalation ──────────────────────────────────────────


class AlertEscalation(SQLModel, table=True):
    """
    Tracks open alerts and their escalation state.
    Background scheduler checks for unacknowledged alerts and escalates.
    """

    __tablename__ = "alert_escalations"

    id: int | None = SQLField(default=None, primary_key=True)
    violation_id: int = SQLField(index=True)
    org_id: str | None = SQLField(default=None, max_length=64, index=True)
    site_id: str | None = SQLField(default=None, max_length=50)
    level: int = SQLField(default=1)  # 1=supervisor 2=safety_officer 3=plant_head 4=emergency
    status: str = SQLField(default="open", max_length=20)  # open|acknowledged|escalated|closed
    notified_at: datetime | None = SQLField(default=None)
    acknowledged_by: str | None = SQLField(default=None, max_length=100)
    acknowledged_at: datetime | None = SQLField(default=None)
    escalation_reason: str | None = SQLField(default=None, max_length=200)
    created_at: datetime | None = SQLField(
        default=None,
        sa_column_kwargs={"server_default": "CURRENT_TIMESTAMP"},
    )


# ── Permit to Work ────────────────────────────────────────────


class PermitToWork(SQLModel, table=True):
    """Digital permit-to-work — required for high-risk zones."""

    __tablename__ = "permits_to_work"

    id: int | None = SQLField(default=None, primary_key=True)
    permit_id: str = SQLField(max_length=64, unique=True, index=True)
    org_id: str | None = SQLField(default=None, max_length=64, index=True)
    site_id: str | None = SQLField(default=None, max_length=50)
    zone_id: str | None = SQLField(default=None, max_length=64)
    work_type: str = SQLField(max_length=100)  # hot_work, confined_space, electrical, etc.
    worker_id: str | None = SQLField(default=None, max_length=64)
    supervisor_id: str | None = SQLField(default=None, max_length=64)
    status: str = SQLField(
        default="pending", max_length=20
    )  # pending|approved|active|expired|cancelled
    valid_from: datetime | None = SQLField(default=None)
    valid_until: datetime | None = SQLField(default=None)
    approved_by: str | None = SQLField(default=None, max_length=100)
    approved_at: datetime | None = SQLField(default=None)
    qr_code: str | None = SQLField(default=None, max_length=200)
    risk_assessment: str | None = SQLField(default=None)  # JSON
    created_at: datetime | None = SQLField(
        default=None,
        sa_column_kwargs={"server_default": "CURRENT_TIMESTAMP"},
    )


# ── Attendance / Headcount ────────────────────────────────────


class WorkerAttendance(SQLModel, table=True):
    """Worker check-in / check-out log from face recognition."""

    __tablename__ = "worker_attendance"

    id: int | None = SQLField(default=None, primary_key=True)
    worker_id: str = SQLField(max_length=64, index=True)
    org_id: str | None = SQLField(default=None, max_length=64, index=True)
    site_id: str | None = SQLField(default=None, max_length=50)
    shift_id: int | None = SQLField(default=None)
    check_in: datetime | None = SQLField(default=None)
    check_out: datetime | None = SQLField(default=None)
    entry_method: str = SQLField(
        default="face_recognition", max_length=30
    )  # face_recognition|manual|qr
    entry_camera_id: str | None = SQLField(default=None, max_length=64)
    exit_camera_id: str | None = SQLField(default=None, max_length=64)
    created_at: datetime | None = SQLField(
        default=None,
        sa_column_kwargs={"server_default": "CURRENT_TIMESTAMP"},
    )


# ── Billing ───────────────────────────────────────────────────


class BillingSubscription(SQLModel, table=True):
    """Subscription billing record per org."""

    __tablename__ = "billing_subscriptions"

    id: int | None = SQLField(default=None, primary_key=True)
    org_id: str = SQLField(max_length=64, unique=True, index=True)
    plan: str = SQLField(max_length=20)
    billing_cycle: str = SQLField(default="monthly", max_length=10)
    amount_paise: int = SQLField(default=0)  # Razorpay uses paise (1 INR = 100 paise)
    currency: str = SQLField(default="INR", max_length=3)
    razorpay_sub_id: str | None = SQLField(default=None, max_length=100)
    status: str = SQLField(default="trial", max_length=20)
    current_period_start: datetime | None = SQLField(default=None)
    current_period_end: datetime | None = SQLField(default=None)
    cancelled_at: datetime | None = SQLField(default=None)
    created_at: datetime | None = SQLField(
        default=None,
        sa_column_kwargs={"server_default": "CURRENT_TIMESTAMP"},
    )


# ── API response models ───────────────────────────────────────


class DetectionOut(BaseModel):
    """Single detection in one video frame, enriched with tracking info."""

    model_config = ConfigDict(from_attributes=True)

    track_id: int = Field(ge=0, description="Stable track ID assigned by ByteTrack")
    class_name: str = Field(max_length=_MAX_CLASS_NAME_LEN, description="Detected PPE class name")
    confidence: float = Field(ge=0.0, le=1.0, description="Detection confidence score")
    bbox_xyxy: tuple[float, float, float, float] = Field(
        description="Bounding box [x1, y1, x2, y2] in pixels",
    )
    zone_id: str | None = Field(
        default=None,
        max_length=_MAX_ZONE_ID_LEN,
        description="Zone the detection falls in, if any",
    )
    is_violation: bool = Field(description="True if this class represents a PPE violation")
    frame_idx: int = Field(ge=0, description="Frame number in the video stream")

    @field_validator("bbox_xyxy")
    @classmethod
    def validate_bbox(
        cls, v: tuple[float, float, float, float]
    ) -> tuple[float, float, float, float]:
        x1, y1, x2, y2 = v
        if x1 >= x2 or y1 >= y2:
            raise ValueError("bbox must satisfy x1<x2 and y1<y2")
        return v


class ViolationEventOut(BaseModel):
    """Persisted violation event returned by the detections API."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 42,
                "track_id": 7,
                "class_name": "no hardhat",
                "confidence": 0.91,
                "zone_id": "zone-entrance",
                "bbox_x1": 120.5,
                "bbox_y1": 80.0,
                "bbox_x2": 240.5,
                "bbox_y2": 210.0,
                "frame_idx": 1500,
                "timestamp": "2024-01-15T09:23:11+00:00",
                "acknowledged": False,
                "notes": None,
            }
        },
    )

    id: int = Field(ge=1, description="Database primary key")
    track_id: int = Field(ge=0, description="ByteTrack track ID")
    class_name: str = Field(max_length=_MAX_CLASS_NAME_LEN, description="PPE violation class")
    confidence: float = Field(ge=0.0, le=1.0)
    zone_id: str | None = Field(default=None, max_length=_MAX_ZONE_ID_LEN)
    bbox_x1: float = Field(ge=_MIN_COORD, le=_MAX_COORD)
    bbox_y1: float = Field(ge=_MIN_COORD, le=_MAX_COORD)
    bbox_x2: float = Field(ge=_MIN_COORD, le=_MAX_COORD)
    bbox_y2: float = Field(ge=_MIN_COORD, le=_MAX_COORD)
    frame_idx: int = Field(ge=0)
    timestamp: datetime = Field(description="UTC timestamp of detection")
    acknowledged: bool = Field(description="True if reviewed by a supervisor")
    notes: str | None = Field(
        default=None, max_length=_MAX_NOTES_LEN, description="Supervisor review notes"
    )


class ViolationAcknowledge(BaseModel):
    """Request body for acknowledging a violation."""

    notes: str | None = Field(
        default=None,
        max_length=_MAX_NOTES_LEN,
        description="Optional supervisor notes. Empty string is normalised to null.",
    )

    @field_validator("notes", mode="before")
    @classmethod
    def normalise_empty_notes(cls, v: str | None) -> str | None:
        if isinstance(v, str) and not v.strip():
            return None
        return v


class StreamFrameMessage(BaseModel):
    """
    JSON envelope pushed over WebSocket for every video frame.

    Consumers should check `type` before processing:
    - "frame" → video frame with jpeg_b64 payload
    - "pong"  → keepalive response
    """

    model_config = ConfigDict(from_attributes=True)

    type: str = Field(default="frame", description="Message type: 'frame' or 'pong'")
    timestamp: datetime = Field(description="UTC timestamp of frame capture")
    frame_idx: int = Field(ge=0, description="Sequential frame number")
    jpeg_b64: str = Field(description="Base64-encoded JPEG of annotated frame")
    active_tracks: int = Field(ge=0, description="Number of persons tracked in this frame")
    active_violations: int = Field(ge=0, description="Number of PPE violations in this frame")
    fps: float = Field(ge=0.0, description="Current pipeline FPS")


class ZoneRiskOut(BaseModel):
    """Risk assessment for one registered zone."""

    zone_id: str = Field(max_length=_MAX_ZONE_ID_LEN, description="Zone identifier")
    mean_intensity: float = Field(ge=0.0, le=1.0, description="Mean heatmap intensity in zone")
    max_intensity: float = Field(ge=0.0, le=1.0, description="Peak heatmap intensity in zone")
    violation_pct: float = Field(
        ge=0.0, le=1.0, description="Fraction of zone above risk threshold"
    )
    risk_level: RiskLevel = Field(description="Categorical risk level")


class HeatmapStats(BaseModel):
    """Internal heatmap accumulator statistics."""

    frame_count: int = Field(ge=0)
    accumulator_max: float = Field(ge=0.0)
    accumulator_mean: float = Field(ge=0.0)
    zones_registered: int = Field(ge=0)
    kernel_cache_size: int = Field(ge=0)
    max_history_len: int = Field(ge=0)


class HeatmapResponse(BaseModel):
    """Heatmap metadata and per-zone risk scores."""

    frame_count: int = Field(ge=0, description="Total frames accumulated")
    stats: HeatmapStats = Field(description="Accumulator statistics")
    zone_risks: list[ZoneRiskOut] = Field(description="Per-zone risk assessments")


class TopRegion(BaseModel):
    """One high-SHAP-value spatial region in a detection crop."""

    zone: str = Field(description="Region label or spatial zone name")
    shap_value: float = Field(description="SHAP contribution value for this region")


class SHAPResponse(BaseModel):
    """SHAP saliency explanation for one detection."""

    track_id: int = Field(ge=0, description="Track ID that was explained")
    class_name: str = Field(max_length=_MAX_CLASS_NAME_LEN, description="Detected class")
    confidence: float = Field(ge=0.0, le=1.0)
    saliency_b64: str = Field(description="Base64-encoded PNG saliency overlay")
    top_regions: list[TopRegion] = Field(description="Top contributing spatial regions")


class SystemStatus(BaseModel):
    """Pipeline and system health status."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ok",
                "pipeline_running": True,
                "active_tracks": 3,
                "fps": 24.7,
                "uptime_s": 3600.0,
                "model_path": "models/best.pt",
                "device": "cpu",
                "video_source": "0",
            }
        }
    )

    status: str = Field(description="'ok' when API is healthy, 'degraded' otherwise")
    pipeline_running: bool = Field(description="True if inference pipeline is running")
    active_tracks: int = Field(ge=0)
    fps: float = Field(ge=0.0)
    uptime_s: float = Field(ge=0.0, description="Seconds since API startup")
    model_path: str = Field(description="Path to loaded model weights")
    device: str = Field(description="Inference device: cpu or cuda")
    video_source: str = Field(description="Video source identifier")


class VideoSourceUpdate(BaseModel):
    """
    Request body to switch the active video source at runtime.
    Accepts a device index ('0'), RTSP URL, or file path.
    """

    source: str = Field(
        description="Video source: integer device index, RTSP URL, or file path",
        min_length=1,
        max_length=500,
    )

    @field_validator("source")
    @classmethod
    def validate_source(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("source must not be blank")
        # Allow: device index, RTSP/HTTP URL, or file path
        if not (
            v.isdigit()
            or v.startswith(("rtsp://", "rtmps://", "http://", "https://"))
            or "/" in v
            or "\\" in v
        ):
            raise ValueError(
                "source must be a device index (e.g. '0'), " "RTSP/HTTP URL, or file path"
            )
        return v


class PaginationParams(BaseModel):
    """Standard pagination and filtering parameters."""

    limit: int = Field(default=50, ge=1, le=500, description="Max results to return")
    offset: int = Field(default=0, ge=0, description="Number of results to skip")
    zone_id: str | None = Field(
        default=None,
        max_length=_MAX_ZONE_ID_LEN,
        description="Filter by zone ID",
    )
    class_name: str | None = Field(
        default=None,
        max_length=_MAX_CLASS_NAME_LEN,
        description="Filter by violation class",
    )
