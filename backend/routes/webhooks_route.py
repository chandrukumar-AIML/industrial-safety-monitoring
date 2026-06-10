"""
backend/routes/webhooks_route.py

Webhook management API — CRUD for outbound webhook registrations.

Endpoints:
  POST   /webhooks            — register a new webhook
  GET    /webhooks            — list all registered webhooks
  PUT    /webhooks/{id}       — update webhook config
  DELETE /webhooks/{id}       — remove webhook
  POST   /webhooks/{id}/test  — send a test event
  GET    /webhooks/stats      — delivery statistics
"""

from __future__ import annotations

import json
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession
from loguru import logger

from ..database import get_session
from ..webhooks.dispatcher import (
    WebhookConfig, WebhookEvent, WebhookType,
    get_webhook_dispatcher,
)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_VALID_EVENTS = [e.value for e in WebhookEvent]
_VALID_TYPES = [t.value for t in WebhookType]


# ── Request / Response models ──────────────────────────────────

class WebhookCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=8, max_length=500)
    webhook_type: str = Field(default="custom")
    events: List[str] = Field(default=["violation.critical", "fire.emergency"])
    secret: Optional[str] = Field(default=None, max_length=200)
    active: bool = True

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith("https://"):
            raise ValueError("Webhook URL must use HTTPS")
        return v

    @field_validator("webhook_type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in _VALID_TYPES:
            raise ValueError(f"webhook_type must be one of: {_VALID_TYPES}")
        return v

    @field_validator("events")
    @classmethod
    def validate_events(cls, v: List[str]) -> List[str]:
        invalid = [e for e in v if e not in _VALID_EVENTS]
        if invalid:
            raise ValueError(f"Invalid events: {invalid}. Valid: {_VALID_EVENTS}")
        return v


class WebhookOut(BaseModel):
    id: int
    name: str
    url: str
    webhook_type: str
    events: List[str]
    active: bool
    created_at: str


# ── Endpoints ─────────────────────────────────────────────────

@router.post("", status_code=201, response_model=WebhookOut)
async def create_webhook(
    body: WebhookCreateRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Register a new outbound webhook."""
    result = await session.execute(
        text("""
            INSERT INTO webhooks
                (name, url, webhook_type, events, secret, active, created_at)
            VALUES
                (:name, :url, :type, :events, :secret, :active, CURRENT_TIMESTAMP)
            RETURNING id, created_at
        """),
        {
            "name": body.name,
            "url": body.url,
            "type": body.webhook_type,
            "events": json.dumps(body.events),
            "secret": body.secret,
            "active": body.active,
        },
    )
    row = result.mappings().first()
    await session.commit()
    logger.info("Webhook registered | name={} | type={}", body.name, body.webhook_type)
    return {
        "id": row["id"],
        "name": body.name,
        "url": body.url,
        "webhook_type": body.webhook_type,
        "events": body.events,
        "active": body.active,
        "created_at": str(row["created_at"]),
    }


@router.get("", response_model=List[WebhookOut])
async def list_webhooks(
    active_only: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
) -> list:
    """List all registered webhooks."""
    where = "WHERE active = 1" if active_only else ""
    result = await session.execute(
        text(f"SELECT id, name, url, webhook_type, events, active, created_at FROM webhooks {where} ORDER BY id"),
    )
    return [
        {
            **dict(row),
            "events": json.loads(row["events"]) if isinstance(row["events"], str) else row["events"],
            "created_at": str(row["created_at"]),
        }
        for row in result.mappings().all()
    ]


@router.put("/{webhook_id}", response_model=WebhookOut)
async def update_webhook(
    webhook_id: int,
    body: WebhookCreateRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Update an existing webhook configuration."""
    result = await session.execute(
        text("""
            UPDATE webhooks SET
                name=:name, url=:url, webhook_type=:type,
                events=:events, secret=:secret, active=:active
            WHERE id=:id
            RETURNING id, created_at
        """),
        {
            "name": body.name, "url": body.url, "type": body.webhook_type,
            "events": json.dumps(body.events), "secret": body.secret,
            "active": body.active, "id": webhook_id,
        },
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(404, "Webhook not found")
    await session.commit()
    return {
        "id": row["id"],
        "name": body.name, "url": body.url,
        "webhook_type": body.webhook_type, "events": body.events,
        "active": body.active, "created_at": str(row["created_at"]),
    }


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Delete a webhook registration."""
    result = await session.execute(
        text("DELETE FROM webhooks WHERE id=:id RETURNING id"),
        {"id": webhook_id},
    )
    if not result.first():
        raise HTTPException(404, "Webhook not found")
    await session.commit()
    logger.info("Webhook deleted | id={}", webhook_id)


@router.post("/{webhook_id}/test")
async def test_webhook(
    webhook_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Send a test payload to verify the webhook endpoint."""
    result = await session.execute(
        text("SELECT id, name, url, webhook_type, events, secret, active FROM webhooks WHERE id=:id"),
        {"id": webhook_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(404, "Webhook not found")

    events_list = json.loads(row["events"]) if isinstance(row["events"], str) else row["events"]
    config = WebhookConfig(
        id=row["id"],
        name=row["name"],
        url=row["url"],
        webhook_type=WebhookType(row["webhook_type"]),
        events=[WebhookEvent(e) for e in events_list],
        secret=row["secret"] or "",
        active=True,  # Force active for test
    )

    test_data = {
        "class_name": "no helmet",
        "severity": "HIGH",
        "zone_id": "zone-a",
        "confidence": 0.92,
        "track_id": 42,
        "timestamp": "2025-01-01T12:00:00+00:00",
        "test": True,
    }

    dispatcher = get_webhook_dispatcher()
    delivery = await dispatcher.dispatch(config, WebhookEvent.VIOLATION_HIGH, test_data)

    return {
        "success": delivery.success,
        "status_code": delivery.status_code,
        "attempts": delivery.attempts,
        "error": delivery.error,
    }


@router.get("/stats/summary")
async def webhook_stats() -> dict:
    """Webhook dispatcher delivery statistics."""
    dispatcher = get_webhook_dispatcher()
    return dispatcher.get_stats()
