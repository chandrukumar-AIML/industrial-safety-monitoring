"""
rag/ingest/ingest_violations.py

Pulls violation events from PostgreSQL and ingests them
into ChromaDB as searchable documents.

# FIXED: Input validation + sanitization for all public methods
# FIXED: Config validation at module load
# IMPROVED: Parameterized queries only — no SQL injection
# IMPROVED: Dependency injection for testability
# FIXED: No PII leakage in logs

Run manually:  python -m rag.ingest.ingest_violations
Schedule via:  cron / GitHub Actions nightly job
"""

from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any, Protocol, runtime_checkable

from langchain_core.documents import Document
from loguru import logger
from pydantic import BaseModel, Field, field_validator  # FIXED: Pydantic v2 compatibility

# ── Config: Load from env with validation ─────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://user:password@localhost/safety_monitor"
)
if not DATABASE_URL.startswith(("postgresql://", "postgresql+asyncpg://")):
    logger.warning("DATABASE_URL may be invalid — using default")
    DATABASE_URL = "postgresql+asyncpg://user:password@localhost/safety_monitor"

# ── Protocol for dependency injection ─────────────────────────
@runtime_checkable
class DBSessionProtocol(Protocol):
    """Protocol for DB session — enables mocking in tests."""
    async def execute(self, query, params: Optional[Dict] = None): ...

# ── Pydantic models for structured validation ─────────────────
class IngestViolationsConfig(BaseModel):
    """Validated configuration for violation ingestion."""
    database_url: str = Field(default=DATABASE_URL)
    days_back: int = Field(default=30, ge=1, le=365)
    
    @field_validator("database_url")
    @classmethod
    def validate_url(cls, v):
        if not v.startswith(("postgresql://", "postgresql+asyncpg://")):
            raise ValueError("database_url must start with postgresql://")
        return v

def _violation_to_document(row: dict) -> Document:
    """
    Convert a PostgreSQL violation row to a LangChain Document.
    The page_content is a natural-language summary — this is what
    gets embedded and searched.
    
    # FIXED: Input validation + sanitization
    """
    # Validate row data
    if not row.get("timestamp"):
        raise ValueError("Violation row missing timestamp")
    if not row.get("class_name"):
        raise ValueError("Violation row missing class_name")
    
    # Format timestamp safely
    ts = row["timestamp"]
    if hasattr(ts, 'strftime'):
        ts_str = ts.strftime('%Y-%m-%d %H:%M')
    else:
        ts_str = str(ts)[:16]
    
    # Build content with sanitized values
    zone_id = row.get("zone_id") or "unspecified"
    # Sanitize zone_id to prevent injection
    if zone_id != "unspecified" and not re.match(r'^[a-zA-Z0-9_\-]+$', zone_id):
        logger.warning("Invalid zone_id: {} — using 'unspecified'", zone_id)
        zone_id = "unspecified"
    
    content = (
        f"PPE violation detected on {ts_str}. "
        f"Worker track ID {row['track_id']} was found without {row['class_name']} "
        f"in zone {zone_id}. "
        f"Detection confidence: {row['confidence']:.0%}. "
        f"Violation was {'acknowledged' if row['acknowledged'] else 'unacknowledged'}."
    )
    
    metadata = {
        "source": "violation_log",
        "timestamp": row["timestamp"].isoformat() if hasattr(row["timestamp"], 'isoformat') else str(row["timestamp"]),
        "track_id": str(row["track_id"]),
        "class_name": row["class_name"],
        "zone_id": zone_id,
        "confidence": round(row["confidence"], 3),
        "acknowledged": row["acknowledged"],
        "doc_id": f"violation_{row['id']}",
    }
    
    return Document(page_content=content, metadata=metadata)


async def ingest_violations(
    session: DBSessionProtocol,
    days_back: int = 30,
    config: Optional[IngestViolationsConfig] = None,
) -> int:
    """
    Ingest the last `days_back` days of violations into ChromaDB.
    
    # FIXED: Parameterized queries only — no SQL injection
    # IMPROVED: Dependency injection for testability
    
    Args:
        session: DB session protocol instance
        days_back: How many days of history to pull (default: 30).
        config: Optional override config.
        
    Returns:
        Number of documents ingested.
    """
    cfg = config or IngestViolationsConfig()
    
    # Validate inputs
    if not 1 <= days_back <= 365:
        logger.warning("days_back out of range: {} — using 30", days_back)
        days_back = 30
    
    since = datetime.now(timezone.utc) - timedelta(days=days_back)
    
    from sqlalchemy import text
    
    query = text("""
        SELECT id, track_id, class_name, confidence,
               zone_id, frame_idx, timestamp, acknowledged
        FROM violation_events
        WHERE timestamp >= :since
        ORDER BY timestamp DESC
        LIMIT 2000
    """)
    
    result = await session.execute(query, {"since": since})
    rows = result.mappings().all()
    
    logger.info(
        "Pulled {} violations from PostgreSQL (last {} days)",
        len(rows), days_back,
    )
    
    if not rows:
        logger.warning("No violations found — nothing to ingest")
        return 0
    
    # Convert to documents
    docs = []
    for row in rows:
        try:
            doc = _violation_to_document(dict(row))
            docs.append(doc)
        except Exception as exc:
            logger.warning("Failed to convert violation row: {} — skipping", exc)
            continue
    
    if not docs:
        logger.warning("No valid documents to ingest")
        return 0
    
    # Add to vector store
    from rag.vector_store import add_documents, COL_VIOLATIONS
    return add_documents(COL_VIOLATIONS, docs)


if __name__ == "__main__":
    # Simple CLI for manual ingestion
    import sys
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.ext.asyncio import AsyncSession
    
    # Create async session
    engine = create_async_engine(DATABASE_URL, echo=False)
    AsyncSessionLocal = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async def main():
        async with AsyncSessionLocal() as session:
            count = await ingest_violations(session, days_back=30)
            print(f"Ingested {count} violation documents into ChromaDB")
    
    asyncio.run(main())