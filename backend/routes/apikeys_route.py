"""
backend/routes/apikeys_route.py

API Key Management UI — create, list, and revoke API keys.

Used by:
  - Admin panel to provision client API keys
  - Multi-tenant setups (one key per client company)
  - CI/CD pipeline integration tokens
  - Webhook verification tokens

Endpoints:
  POST   /apikeys            — create new API key
  GET    /apikeys            — list all API keys (masked)
  DELETE /apikeys/{id}       — revoke (delete) an API key
  POST   /apikeys/{id}/rotate — rotate key (delete + create new)

Security:
  - Keys are stored as SHA-256 hashes — never stored in plaintext
  - Key value shown ONCE at creation — not retrievable afterward
  - Requires ADMIN role to manage
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession
from loguru import logger

from ..database import get_session
from ..auth.rbac import Role, require_role

router = APIRouter(prefix="/apikeys", tags=["api-keys"])

_VALID_ROLES = ["viewer", "operator", "manager", "admin"]


def _generate_key() -> str:
    """Generate a secure prefixed API key."""
    return "sm_" + secrets.token_urlsafe(32)


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _mask_key(key_hash: str) -> str:
    """Show only first 8 chars of hash for display."""
    return key_hash[:8] + "..." + key_hash[-4:]


# ── Models ────────────────────────────────────────────────────

class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100, description="Human-readable label")
    role: str = Field(default="viewer", description="viewer | operator | manager | admin")
    description: Optional[str] = Field(default=None, max_length=500)
    expires_days: Optional[int] = Field(default=None, ge=1, le=3650,
                                        description="Days until expiry; null = never expires")

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in _VALID_ROLES:
            raise ValueError(f"role must be one of: {_VALID_ROLES}")
        return v


class ApiKeyOut(BaseModel):
    id: int
    name: str
    role: str
    description: Optional[str]
    key_preview: str  # masked hash, not the actual key
    expires_at: Optional[str]
    active: bool
    created_at: str


class ApiKeyCreated(ApiKeyOut):
    """Returned only at creation time — includes the plaintext key."""
    key: str = Field(description="Store this securely — shown only once!")


# ── Endpoints ─────────────────────────────────────────────────

@router.post("", status_code=201, response_model=ApiKeyCreated)
async def create_api_key(
    body: ApiKeyCreateRequest,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_role(Role.ADMIN)),
) -> dict:
    """Create a new API key. The plaintext key is shown ONCE — store it safely."""
    raw_key = _generate_key()
    key_hash = _hash_key(raw_key)

    expires_at = None
    if body.expires_days:
        from datetime import timedelta
        expires_at = (datetime.now(timezone.utc) + timedelta(days=body.expires_days)).isoformat()

    result = await session.execute(
        text("""
            INSERT INTO api_keys
                (name, role, description, key_hash, expires_at, active)
            VALUES
                (:name, :role, :description, :key_hash, :expires_at, TRUE)
            RETURNING id, created_at
        """),
        {
            "name": body.name,
            "role": body.role,
            "description": body.description,
            "key_hash": key_hash,
            "expires_at": expires_at,
        },
    )
    row = result.mappings().first()
    await session.commit()
    logger.info("API key created | name={} | role={}", body.name, body.role)

    return {
        "id": row["id"],
        "name": body.name,
        "role": body.role,
        "description": body.description,
        "key_preview": _mask_key(key_hash),
        "key": raw_key,  # Only time this is shown!
        "expires_at": expires_at,
        "active": True,
        "created_at": str(row["created_at"]),
    }


@router.get("", response_model=List[ApiKeyOut])
async def list_api_keys(
    role: Optional[str] = Query(default=None),
    active_only: bool = Query(default=True),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_role(Role.ADMIN)),
) -> list:
    """List all API keys (masked — plaintext never returned after creation)."""
    conditions = []
    params: dict = {"limit": limit, "offset": offset}

    if active_only:
        conditions.append("active = 1")
    if role:
        if role not in _VALID_ROLES:
            raise HTTPException(422, f"role must be one of: {_VALID_ROLES}")
        conditions.append("role = :role")
        params["role"] = role

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    result = await session.execute(
        text(f"""
            SELECT id, name, role, description, key_hash, expires_at, active, created_at
            FROM api_keys {where}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """),
        params,
    )
    rows = result.mappings().all()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "role": r["role"],
            "description": r["description"],
            "key_preview": _mask_key(r["key_hash"]),
            "expires_at": str(r["expires_at"]) if r["expires_at"] else None,
            "active": r["active"],
            "created_at": str(r["created_at"]),
        }
        for r in rows
    ]


@router.delete("/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: int,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_role(Role.ADMIN)),
):
    """Revoke (permanently delete) an API key."""
    result = await session.execute(
        text("DELETE FROM api_keys WHERE id=:id RETURNING id, name"),
        {"id": key_id},
    )
    row = result.first()
    if not row:
        raise HTTPException(404, "API key not found")
    await session.commit()
    logger.info("API key revoked | id={} | name={}", key_id, row[1])


@router.post("/{key_id}/rotate", response_model=ApiKeyCreated)
async def rotate_api_key(
    key_id: int,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_role(Role.ADMIN)),
) -> dict:
    """Rotate an API key — revoke old and generate new key with same config."""
    # Get existing config
    existing = await session.execute(
        text("SELECT name, role, description, expires_at FROM api_keys WHERE id=:id AND active=1"),
        {"id": key_id},
    )
    old_row = existing.mappings().first()
    if not old_row:
        raise HTTPException(404, "API key not found or already revoked")

    # Revoke old
    await session.execute(
        text("DELETE FROM api_keys WHERE id=:id"),
        {"id": key_id},
    )

    # Create new
    raw_key = _generate_key()
    key_hash = _hash_key(raw_key)

    result = await session.execute(
        text("""
            INSERT INTO api_keys
                (name, role, description, key_hash, expires_at, active)
            VALUES
                (:name, :role, :description, :key_hash, :expires_at, TRUE)
            RETURNING id, created_at
        """),
        {
            "name": old_row["name"],
            "role": old_row["role"],
            "description": old_row["description"],
            "key_hash": key_hash,
            "expires_at": old_row["expires_at"],
        },
    )
    new_row = result.mappings().first()
    await session.commit()
    logger.info("API key rotated | old_id={} | new_id={} | name={}", key_id, new_row["id"], old_row["name"])

    return {
        "id": new_row["id"],
        "name": old_row["name"],
        "role": old_row["role"],
        "description": old_row["description"],
        "key_preview": _mask_key(key_hash),
        "key": raw_key,
        "expires_at": str(old_row["expires_at"]) if old_row["expires_at"] else None,
        "active": True,
        "created_at": str(new_row["created_at"]),
    }
