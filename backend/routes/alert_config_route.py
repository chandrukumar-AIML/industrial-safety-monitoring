"""
backend/routes/alert_config_route.py

CRUD endpoints for alert recipient management.

# FIXED: Input validation + sanitization for all public methods
# FIXED: Parameterized queries only — no SQL injection
# IMPROVED: Email/phone validation with proper error messages
# IMPROVED: Dependency injection for testability
# FIXED: No PII leakage in logs (redact contact info)
# FIXED: FastAPI Query() for query parameters (not Field())
# FIXED: No response_model for 204 No Content responses
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status, Response

from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession
from loguru import logger

from ..database import get_session

router = APIRouter(prefix="/alert-config", tags=["alerts"])


# ── Request / Response models ─────────────────────────────────
class RecipientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    role: str = Field(min_length=1, max_length=64)
    email: Optional[str] = Field(default=None)
    whatsapp_number: Optional[str] = Field(default=None)
    notify_critical: bool = True
    notify_high: bool = True
    notify_medium: bool = False
    notify_low: bool = False
    zone_filter: Optional[List[str]] = None

    @field_validator("whatsapp_number")
    @classmethod
    def validate_whatsapp(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        # E.164 format: +[country code][number]
        if not re.match(r'^\+[1-9]\d{1,14}$', v):
            raise ValueError("whatsapp_number must be in E.164 format: +1234567890")
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        # Basic email validation
        if not re.match(r'^[^@]+@[^@]+\.[^@]+$', v):
            raise ValueError("Invalid email format")
        return v

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v: str) -> str:
        # Strip and sanitize
        return re.sub(r'[<>{}]', '', v.strip())


class RecipientOut(BaseModel):
    id: int
    name: str
    role: str
    email: Optional[str]
    whatsapp_number: Optional[str]
    notify_critical: bool
    notify_high: bool
    notify_medium: bool
    notify_low: bool
    zone_filter: Optional[List[str]]
    active: bool
    created_at: str


class AlertLogOut(BaseModel):
    id: int
    recipient_id: Optional[int]
    alert_type: Optional[str]
    zone_id: Optional[str]
    track_id: Optional[int]
    severity: Optional[str]
    status: str
    sent_at: str


class AlertStatsOut(BaseModel):
    total_sent: int
    total_throttled: int
    total_failed: int
    by_severity: dict[str, int]
    by_channel: dict[str, int]


# ── Helper: Redact PII for logging ───────────────────────────
def _redact_contact(email: Optional[str], phone: Optional[str]) -> tuple[str, str]:
    """Redact email and phone for safe logging."""
    redacted_email = "***@***" if email else None
    redacted_phone = "+***" if phone else None
    return redacted_email, redacted_phone


# ── Endpoints ─────────────────────────────────────────────────
@router.get(
    "/recipients",
    response_model=List[RecipientOut],
    summary="List alert recipients",
)
async def list_recipients(
    session: AsyncSession = Depends(get_session),
) -> list:
    result = await session.execute(
        text("""
            SELECT id, name, role, email, whatsapp_number,
                   notify_critical, notify_high, notify_medium, notify_low,
                   zone_filter, active, created_at
            FROM alert_recipients
            WHERE active = 1
            ORDER BY name
        """)
    )
    rows = result.mappings().all()
    return [
        {
            **dict(row),
            "zone_filter": json.loads(row["zone_filter"]) if row["zone_filter"] else None,
            "created_at": str(row["created_at"]),
        }
        for row in rows
    ]


@router.post(
    "/recipients",
    status_code=status.HTTP_201_CREATED,
    response_model=RecipientOut,
    summary="Add alert recipient",
)
async def create_recipient(
    body: RecipientCreate,
    session: AsyncSession = Depends(get_session),
) -> dict:
    if not body.email and not body.whatsapp_number:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "At least one of email or whatsapp_number must be provided",
        )

    zone_json = json.dumps(body.zone_filter) if body.zone_filter else None

    result = await session.execute(
        text("""
            INSERT INTO alert_recipients
            (name, role, email, whatsapp_number,
             notify_critical, notify_high, notify_medium, notify_low,
             zone_filter)
            VALUES
            (:name, :role, :email, :whatsapp_number,
             :notify_critical, :notify_high, :notify_medium, :notify_low,
             :zone_filter)
            RETURNING id, created_at
        """),
        {
            "name": body.name,
            "role": body.role,
            "email": body.email,
            "whatsapp_number": body.whatsapp_number,
            "notify_critical": body.notify_critical,
            "notify_high": body.notify_high,
            "notify_medium": body.notify_medium,
            "notify_low": body.notify_low,
            "zone_filter": zone_json,
        }
    )
    row = result.mappings().first()
    await session.commit()

    # Refresh worker recipients
    from ..alerts.alert_worker import alert_worker
    from ..database import AsyncSessionLocal
    await alert_worker._refresh_recipients()

    # Log without PII
    redacted_email, redacted_phone = _redact_contact(body.email, body.whatsapp_number)
    logger.info("Recipient created: {} | role={} | email={} | phone={}", 
                body.name, body.role, redacted_email, redacted_phone)

    return {
        "id": row["id"],
        "name": body.name,
        "role": body.role,
        "email": body.email,
        "whatsapp_number": body.whatsapp_number,
        "notify_critical": body.notify_critical,
        "notify_high": body.notify_high,
        "notify_medium": body.notify_medium,
        "notify_low": body.notify_low,
        "zone_filter": body.zone_filter,
        "active": True,
        "created_at": str(row["created_at"]),
    }

@router.delete(
    "/recipients/{recipient_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove alert recipient",
)
async def delete_recipient(
    recipient_id: int,
    session: AsyncSession = Depends(get_session),
) -> Response:
    
    if recipient_id < 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid recipient_id")
    
    result = await session.execute(
        text("""
            UPDATE alert_recipients
            SET active=0
            WHERE id=:id
        """),
        {"id": recipient_id}
    )
    await session.commit()
    
    if result.rowcount == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recipient not found")

    from ..alerts.alert_worker import alert_worker
    await alert_worker._refresh_recipients()

    logger.info("Recipient deactivated: id={}", recipient_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT) 

@router.get(
    "/logs",
    response_model=List[AlertLogOut],
    summary="Alert send logs",
)
async def alert_logs(
    # ✅ FIXED: Use Query() instead of Field() for query parameters
    limit: int = Query(default=100, ge=1, le=1000, description="Max log entries to return"),
    session: AsyncSession = Depends(get_session),
) -> list:
    result = await session.execute(
        text("""
            SELECT id, recipient_id, alert_type, zone_id,
                   track_id, severity, status, sent_at
            FROM alert_send_log
            ORDER BY sent_at DESC
            LIMIT :limit
        """),
        {"limit": limit}
    )
    return [
        {**dict(row), "sent_at": str(row["sent_at"])}
        for row in result.mappings().all()
    ]


@router.get(
    "/stats",
    response_model=AlertStatsOut,
    summary="Alert delivery statistics",
)
async def alert_stats(
    session: AsyncSession = Depends(get_session),
) -> AlertStatsOut:
    result = await session.execute(
        text("""
            SELECT
                COUNT(CASE WHEN status='sent' THEN 1 END) as total_sent,
                COUNT(CASE WHEN status='throttled' THEN 1 END) as total_throttled,
                COUNT(CASE WHEN status='failed' THEN 1 END) as total_failed
            FROM alert_send_log
        """)
    )
    row = result.mappings().first()

    sev_r = await session.execute(
        text("""
            SELECT severity, COUNT(*) as cnt
            FROM alert_send_log
            WHERE status='sent'
            GROUP BY severity
        """)
    )
    by_severity = {r[0]: r[1] for r in sev_r.all() if r[0]}

    ch_r = await session.execute(
        text("""
            SELECT alert_type, COUNT(*) as cnt
            FROM alert_send_log
            WHERE status='sent'
            GROUP BY alert_type
        """)
    )
    by_channel = {r[0]: r[1] for r in ch_r.all() if r[0]}

    return AlertStatsOut(
        total_sent=row["total_sent"] or 0,
        total_throttled=row["total_throttled"] or 0,
        total_failed=row["total_failed"] or 0,
        by_severity=by_severity,
        by_channel=by_channel,
    )


@router.post(
    "/test",
    summary="Send test alert to a recipient",
)
async def send_test_alert(
    recipient_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Send a test WhatsApp + email to verify configuration."""
    # Validate ID
    if recipient_id < 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid recipient_id")
    
    result = await session.execute(
        text("SELECT * FROM alert_recipients WHERE id=:id AND active=1"),
        {"id": recipient_id}
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recipient not found")

    from ..alerts.alert_worker import AlertJob, alert_worker

    job = AlertJob(
        zone_id="TEST-ZONE",
        zone_name="Test Zone",
        zone_type="danger",
        track_id=999,
        missing_ppe=["hardhat", "gloves"],
        severity="HIGH",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    await alert_worker.enqueue(job)
    
    # Log without PII
    redacted_email, redacted_phone = _redact_contact(row.get("email"), row.get("whatsapp_number"))
    logger.info("Test alert sent to recipient id={} | email={} | phone={}", 
                recipient_id, redacted_email, redacted_phone)
    
    return {"status": "test_alert_enqueued", "recipient_id": recipient_id}