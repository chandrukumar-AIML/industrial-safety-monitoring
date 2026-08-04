"""
backend/routes/auth_route.py

Email + password authentication endpoints.
POST /auth/login    — returns JWT
POST /auth/register — creates new user (open registration or admin-only)
GET  /auth/me       — returns current user info from JWT
"""

from __future__ import annotations

import os
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from ..database import get_session
from ..auth.jwt_utils import (
    UserCreate, UserLogin, Token, TokenData,
    hash_password, verify_password, create_access_token, decode_access_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# Set OPEN_REGISTRATION=false to disable self-signup (admin creates users instead)
OPEN_REGISTRATION = os.getenv("OPEN_REGISTRATION", "true").lower() == "true"


async def _get_user_by_email(session: AsyncSession, email: str) -> dict | None:
    result = await session.execute(
        text("SELECT * FROM users WHERE email = :email LIMIT 1"),
        {"email": email.lower().strip()},
    )
    row = result.mappings().first()
    return dict(row) if row else None


@router.post("/login", response_model=Token, summary="Login with email + password")
async def login(body: UserLogin, session: AsyncSession = Depends(get_session)):
    user = await _get_user_by_email(session, body.email)
    if not user or not verify_password(body.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if not user["is_active"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    token = create_access_token({
        "sub": user["email"],
        "role": user["role"],
        "org_id": user["org_id"],
        "user_id": user["id"],
    })
    return Token(
        access_token=token,
        user_email=user["email"],
        role=user["role"],
        org_id=user["org_id"],
    )


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(body: UserCreate, session: AsyncSession = Depends(get_session)):
    if not OPEN_REGISTRATION:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is closed. Contact your admin.",
        )
    existing = await _get_user_by_email(session, body.email)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    hashed = hash_password(body.password)
    result = await session.execute(
        text("""
            INSERT INTO users (email, hashed_password, full_name, role, org_id, is_active)
            VALUES (:email, :pw, :name, :role, :org_id, TRUE)
            RETURNING id, email, role, org_id
        """),
        {
            "email": body.email.lower().strip(),
            "pw": hashed,
            "name": body.full_name,
            "role": body.role,
            "org_id": body.org_id,
        },
    )
    row = result.mappings().first()
    await session.commit()

    token = create_access_token({
        "sub": row["email"],
        "role": row["role"],
        "org_id": row["org_id"],
        "user_id": row["id"],
    })
    return Token(
        access_token=token,
        user_email=row["email"],
        role=row["role"],
        org_id=row["org_id"],
    )


@router.get("/me", summary="Get current user info")
async def me(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    token_data: TokenData | None = decode_access_token(auth.removeprefix("Bearer ").strip())
    if not token_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return {
        "email": token_data.email,
        "role": token_data.role,
        "org_id": token_data.org_id,
    }
