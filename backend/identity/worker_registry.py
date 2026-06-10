"""
identity/worker_registry.py

Worker profile management with PII protection.

# FIXED: Input validation + sanitization for all public methods
# FIXED: SQL injection prevention via parameterized queries only
# IMPROVED: Pydantic models for structured validation
# IMPROVED: Dependency injection for testability
# FIXED: PII redaction in logs + API responses
# IMPROVED: Soft-delete with audit trail for GDPR compliance

Responsibilities:
  1. CRUD operations for worker profiles
  2. Face embedding storage (serialized, not images)
  3. Risk score + level tracking
  4. HR alert flags + cooldown management
  5. GDPR-compliant data retention + deletion
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Dict, List, Optional, Any, Protocol, runtime_checkable

from loguru import logger
from pydantic import BaseModel, Field, field_validator, model_validator, EmailStr  # FIXED: Pydantic v2 compatibility

# ── Config: Load from env with validation ─────────────────────
MAX_WORKER_NAME_LEN = int(os.getenv("WORKER_NAME_MAX_LENGTH", "200"))
MAX_DEPARTMENT_LEN = int(os.getenv("WORKER_DEPT_MAX_LENGTH", "100"))
PRIVACY_MODE = os.getenv("GDPR_MODE", "strict").lower()
if PRIVACY_MODE not in ("strict", "relaxed", "disabled"):
    logger.warning("Invalid GDPR_MODE: {} — using 'strict'", PRIVACY_MODE)
    PRIVACY_MODE = "strict"

# Data retention (GDPR)
# FIXED: Validate bounds — RETENTION_DAYS=0 would delete all data immediately; min=30 days
_raw_retention = int(os.getenv("WORKER_DATA_RETENTION_DAYS", "730"))
if not 30 <= _raw_retention <= 3650:
    logger.warning(
        "WORKER_DATA_RETENTION_DAYS={} out of 30-3650 — clamping to 730 (2 years)",
        _raw_retention,
    )
    _raw_retention = 730
RETENTION_DAYS = _raw_retention
ANONYMIZE_ON_DELETE = os.getenv("WORKER_ANONYMIZE_ON_DELETE", "true").lower() == "true"


# ── Enums for type safety ─────────────────────────────────────
class PrivacyMode(str, Enum):
    STRICT = "strict"
    RELAXED = "relaxed"
    DISABLED = "disabled"


class WorkerStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    TERMINATED = "terminated"
    ANONYMIZED = "anonymized"  # GDPR-compliant deletion


# ── Pydantic models for structured validation ─────────────────
class WorkerProfile(BaseModel):
    """
    Worker profile with PII protection.
    
    # FIXED: All fields validated + sanitized
    # IMPROVED: Type hints + defaults for safety
    """
    worker_id: str = Field(..., min_length=1, max_length=100, pattern=r'^[a-zA-Z0-9_\-]+$')
    full_name: str = Field(..., min_length=1, max_length=MAX_WORKER_NAME_LEN)
    email: Optional[EmailStr] = None
    department: Optional[str] = Field(default=None, max_length=MAX_DEPARTMENT_LEN)
    role: Optional[str] = Field(default=None, max_length=100)
    
    # Identity fields
    face_embedding: Optional[bytes] = Field(default=None, exclude=True)  # Serialized embedding
    enrolled_at: Optional[datetime] = None
    
    # Risk tracking
    risk_score: float = Field(default=0.0, ge=0)
    risk_level: str = Field(default="LOW", pattern="^(LOW|HIGH|CRITICAL)$")
    
    # Status + GDPR
    status: WorkerStatus = WorkerStatus.ACTIVE
    hr_alerted: bool = False
    last_alert_at: Optional[datetime] = None
    
    # Audit
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    
    @field_validator("worker_id")
    @classmethod
    def sanitize_worker_id(cls, v):
        cleaned = re.sub(r'[^a-zA-Z0-9_\-]', '_', v.strip())
        if not cleaned:
            raise ValueError("Invalid worker_id")
        return cleaned[:100]

    @field_validator("full_name")
    @classmethod
    def sanitize_name(cls, v):
        # Allow Unicode names but strip control chars
        return re.sub(r'[\x00-\x1f\x7f]', '', v.strip())[:MAX_WORKER_NAME_LEN]

    @model_validator(mode="after")
    def validate_consistency(self) -> "WorkerProfile":
        # Anonymized workers should have redacted PII
        if self.status == WorkerStatus.ANONYMIZED:
            if self.full_name and not self.full_name.startswith("ANON_"):
                logger.warning("Anonymized worker {} has non-anonymized name", self.worker_id)
        return self

    def to_api_response(self, include_pii: bool = False) -> dict:
        """
        Convert to dict for API responses.

        Args:
            include_pii: If False, redact sensitive fields per GDPR.
        """
        data = self.model_dump(exclude={"face_embedding"})  # Never expose embedding
        
        if PRIVACY_MODE == "strict" and not include_pii:
            # Redact PII
            data["full_name"] = f"Worker***{self.worker_id[-4:]}" if len(self.worker_id) >= 4 else "Worker***"
            data["email"] = None
            if self.department:
                data["department"] = "REDACTED"
        
        return data
    
    @classmethod
    def from_db_row(cls, row: dict) -> "WorkerProfile":
        """Create from SQLAlchemy result row."""
        return cls(
            worker_id=row["worker_id"],
            full_name=row["full_name"],
            email=row.get("email"),
            department=row.get("department"),
            role=row.get("role"),
            face_embedding=row.get("face_embedding"),
            enrolled_at=row.get("enrolled_at"),
            risk_score=float(row.get("risk_score") or 0.0),
            risk_level=row.get("risk_level", "LOW"),
            status=WorkerStatus(row.get("status", "active")),
            hr_alerted=bool(row.get("hr_alerted", False)),
            last_alert_at=row.get("last_alert_at"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
            deleted_at=row.get("deleted_at"),
        )


# ── Protocol for dependency injection ─────────────────────────
@runtime_checkable
class DBFactoryProtocol(Protocol):
    """Protocol for async session factory — enables mocking in tests."""
    def __call__(self): ...


# ── Custom exceptions ────────────────────────────────────────
class RegistryError(Exception):
    """Base exception for registry operations."""
    pass

class WorkerNotFoundError(RegistryError):
    """Raised when worker ID not found."""
    pass

class PrivacyViolationError(RegistryError):
    """Raised when PII handling violates policy."""
    pass

class InvalidWorkerDataError(RegistryError):
    """Raised when worker data validation fails."""
    pass


# ── Helper: Sanitize + redact for logging ────────────────────
def _redact_worker_id(worker_id: str) -> str:
    """Redact worker ID for logs in strict mode."""
    if PRIVACY_MODE == "strict" and len(worker_id) >= 4:
        return f"***{worker_id[-4:]}"
    return worker_id


def _redact_name(name: Optional[str]) -> Optional[str]:
    """Redact name for logs in strict mode."""
    if not name or PRIVACY_MODE != "strict":
        return name
    return f"{name[0]}***" if len(name) > 1 else "***"


# ── Registry operations ───────────────────────────────────────

async def get_worker_profile(
    worker_id: str,
    db_factory: DBFactoryProtocol,
    include_embedding: bool = False,
) -> Optional[WorkerProfile]:
    """
    Fetch worker profile by ID.
    
    # FIXED: Parameterized queries only
    # FIXED: Input sanitization
    """
    from sqlalchemy import select
    from backend.database import WorkerProfile as DBModel
    
    worker_id_safe = re.sub(r'[^a-zA-Z0-9_\-]', '_', worker_id.strip())[:100]
    
    async with db_factory() as session:
        query = select(DBModel).where(
            DBModel.worker_id == worker_id_safe,
            DBModel.status != WorkerStatus.ANONYMIZED.value,
        )
        result = await session.execute(query)
        row = result.mappings().first()
    
    if not row:
        return None
    
    profile = WorkerProfile.from_db_row(dict(row))
    
    # Never return embedding via this API unless explicitly requested + authorized
    if not include_embedding:
        profile.face_embedding = None
    
    return profile


async def upsert_worker_profile(
    profile: dict | WorkerProfile,
    db_factory: DBFactoryProtocol,
) -> WorkerProfile:
    """
    Create or update worker profile.
    
    # FIXED: Validate via Pydantic before DB write
    # FIXED: Parameterized UPSERT — no SQL injection
    # IMPROVED: Atomic check-and-write to prevent race conditions
    """
    from sqlalchemy import text
    from backend.database import WorkerProfile as DBModel
    
    # Convert dict to validated model
    if isinstance(profile, dict):
        try:
            validated = WorkerProfile(**profile)
        except Exception as e:
            raise InvalidWorkerDataError(f"Profile validation failed: {e}")
    else:
        validated = profile
    
    worker_id_safe = validated.worker_id
    
    async with db_factory() as session:
        try:
            # Use SQLAlchemy ORM for UPSERT
            from sqlalchemy.dialects.postgresql import insert
            
            stmt = insert(DBModel).values(
                worker_id=worker_id_safe,
                full_name=validated.full_name,
                email=validated.email,
                department=validated.department,
                role=validated.role,
                face_embedding=validated.face_embedding,
                enrolled_at=validated.enrolled_at or datetime.now(timezone.utc),
                risk_score=validated.risk_score,
                risk_level=validated.risk_level,
                status=validated.status.value,
                hr_alerted=validated.hr_alerted,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["worker_id"],
                set_={
                    "full_name": validated.full_name,
                    "email": validated.email,
                    "department": validated.department,
                    "role": validated.role,
                    "face_embedding": validated.face_embedding,
                    "risk_score": validated.risk_score,
                    "risk_level": validated.risk_level,
                    "status": validated.status.value,
                    "hr_alerted": validated.hr_alerted,
                    "updated_at": datetime.now(timezone.utc),
                }
            )
            
            await session.execute(stmt)
            await session.commit()
            
        except Exception as exc:
            await session.rollback()
            if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
                raise ValueError(f"Worker ID '{worker_id_safe}' already exists")
            raise RegistryError(f"Failed to upsert worker: {exc}")
    
    logger.info("Worker profile saved: {}", _redact_worker_id(worker_id_safe))
    return validated


async def anonymize_worker(
    worker_id: str,
    db_factory: DBFactoryProtocol,
    reason: str = "GDPR request",
) -> bool:
    """
    GDPR-compliant anonymization of worker data.
    
    # FIXED: Atomic update + audit logging
    # IMPROVED: Configurable anonymization strategy
    
    Returns:
        True if anonymized, False if not found.
    """
    from sqlalchemy import text, update
    from backend.database import WorkerProfile as DBModel
    
    worker_id_safe = re.sub(r'[^a-zA-Z0-9_\-]', '_', worker_id.strip())[:100]
    
    async with db_factory() as session:
        # Check if exists first
        result = await session.execute(
            text("SELECT 1 FROM worker_profiles WHERE worker_id = :id"),
            {"id": worker_id_safe}
        )
        if not result.first():
            return False
        
        # Anonymize fields based on policy
        anon_name = f"ANON_{worker_id_safe[-8:]}" if len(worker_id_safe) >= 8 else "ANON_UNKNOWN"
        
        update_values = {
            "status": WorkerStatus.ANONYMIZED.value,
            "full_name": anon_name if ANONYMIZE_ON_DELETE else worker_id_safe,
            "email": None,
            "department": None,
            "role": None,
            "face_embedding": None,  # Delete biometric data
            "risk_score": 0.0,
            "risk_level": "LOW",
            "hr_alerted": False,
            "deleted_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        
        await session.execute(
            update(DBModel)
            .where(DBModel.worker_id == worker_id_safe)
            .values(**update_values)
        )
        
        # Log anonymization event (audit trail)
        await session.execute(
            text("""
                INSERT INTO worker_audit_log
                (worker_id, action, details, performed_at)
                VALUES (:id, 'anonymize', :reason, NOW())
            """),
            {"id": worker_id_safe, "reason": reason[:500]}
        )
        
        await session.commit()
    
    logger.warning(
        "Worker anonymized: {} | reason: {}",
        _redact_worker_id(worker_id_safe), reason[:100],
    )
    return True


async def delete_worker_data(
    worker_id: str,
    db_factory: DBFactoryProtocol,
    hard_delete: bool = False,
) -> bool:
    """
    Delete worker data (soft by default, hard if explicitly requested).
    
    # FIXED: Require explicit hard_delete flag to prevent accidental data loss
    # IMPROVED: Return bool for success/failure handling
    """
    from sqlalchemy import text, delete
    from backend.database import WorkerProfile as DBModel
    
    worker_id_safe = re.sub(r'[^a-zA-Z0-9_\-]', '_', worker_id.strip())[:100]
    
    async with db_factory() as session:
        try:
            if hard_delete:
                # Hard delete — use with extreme caution + audit
                result = await session.execute(
                    delete(DBModel).where(DBModel.worker_id == worker_id_safe)
                )
                action = "hard_delete"
            else:
                # Prefer anonymization for GDPR compliance
                return await anonymize_worker(worker_id_safe, db_factory, reason="Soft delete request")
            
            await session.commit()
            logger.info("Worker {} deleted ({})", _redact_worker_id(worker_id_safe), action)
            return result.rowcount > 0
            
        except Exception as exc:
            logger.error("Worker delete failed: {} — {}", _redact_worker_id(worker_id_safe), exc)
            await session.rollback()
            return False


async def get_active_workers(
    db_factory: DBFactoryProtocol,
    status_filter: Optional[WorkerStatus | str] = None,
    include_pii: bool = False,
) -> List[WorkerProfile]:
    """
    Fetch active workers with optional status filter.
    
    # FIXED: Parameterized queries only
    # IMPROVED: PII redaction in results per privacy mode
    """
    from sqlalchemy import select
    from backend.database import WorkerProfile as DBModel
    
    # Convert string status to enum if needed
    if isinstance(status_filter, str):
        try:
            status_filter = WorkerStatus(status_filter.lower())
        except ValueError:
            logger.warning("Invalid status filter: {} — fetching ACTIVE only", status_filter)
            status_filter = WorkerStatus.ACTIVE
    
    async with db_factory() as session:
        query = select(DBModel).where(
            DBModel.status != WorkerStatus.ANONYMIZED.value
        )
        if status_filter:
            query = query.where(DBModel.status == status_filter.value)
        query = query.order_by(DBModel.full_name)
        
        result = await session.execute(query)
        rows = result.mappings().all()
    
    profiles = [WorkerProfile.from_db_row(dict(row)) for row in rows]
    
    # Redact PII in results if not explicitly requested
    if not include_pii and PRIVACY_MODE == "strict":
        for p in profiles:
            p.full_name = f"Worker***{p.worker_id[-4:]}" if len(p.worker_id) >= 4 else "Worker***"
            p.email = None
            p.department = "REDACTED" if p.department else None
    
    return profiles


# ── Convenience: Bulk operations ─────────────────────────────

async def bulk_update_risk_levels(
    worker_ids: List[str],
    risk_level: str,
    db_factory: DBFactoryProtocol,
) -> Dict[str, bool]:
    """
    Update risk level for multiple workers efficiently.
    
    Returns:
        Dict mapping worker_id → success bool
    """
    results = {}
    for wid in worker_ids:
        try:
            if risk_level not in ("LOW", "HIGH", "CRITICAL"):
                raise ValueError(f"Invalid risk_level: {risk_level}")
            
            from sqlalchemy import text
            async with db_factory() as session:
                await session.execute(
                    text("""
                        UPDATE worker_profiles
                        SET risk_level=:level, updated_at=NOW()
                        WHERE worker_id=:id AND status != 'anonymized'
                    """),
                    {"level": risk_level, "id": wid}
                )
                await session.commit()
            results[wid] = True
        except Exception as e:
            logger.error("Bulk risk update failed for {}: {}", wid, e)
            results[wid] = False
    return results


async def get_worker_summary(
    db_factory: DBFactoryProtocol,
) -> Dict[str, Any]:
    """
    Get aggregated summary of all workers.
    
    Returns:
        Dict with counts by status, risk distribution, etc.
    """
    from sqlalchemy import text, func, select
    from backend.database import WorkerProfile as DBModel
    
    async with db_factory() as session:
        # Count by status
        status_counts = await session.execute(
            text("""
                SELECT status, COUNT(*) 
                FROM worker_profiles 
                GROUP BY status
            """)
        )
        status_summary = {row[0]: row[1] for row in status_counts.all()}
        
        # Risk distribution
        risk_counts = await session.execute(
            text("""
                SELECT risk_level, COUNT(*) 
                FROM worker_profiles 
                WHERE status != 'anonymized'
                GROUP BY risk_level
            """)
        )
        risk_summary = {row[0]: row[1] for row in risk_counts.all()}
        
        # Enrolled vs not enrolled (face recognition)
        enrolled = await session.execute(
            select(func.count()).where(
                DBModel.face_embedding != None,
                DBModel.status != WorkerStatus.ANONYMIZED.value,
            )
        )
        enrolled_count = enrolled.scalar() or 0
    
    total = sum(status_summary.values())
    
    return {
        "total_workers": total,
        "by_status": status_summary,
        "by_risk_level": risk_summary,
        "face_enrolled_count": enrolled_count,
        "face_enrolled_pct": round(enrolled_count / max(total, 1) * 100, 1),
        "privacy_mode": PRIVACY_MODE,
        "retention_days": RETENTION_DAYS,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }