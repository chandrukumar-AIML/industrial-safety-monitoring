"""
backend/database.py

Async SQLite database setup using SQLModel + aiosqlite.
All application DB access goes through get_session().

# FIXED: Credential masking in logs/errors
# FIXED: Proper engine/session factory separation for testability
# IMPROVED: Connection pooling config for production stability
# FIXED: Clear error messages with masked URLs
# IMPROVED: Dependency injection ready for testing
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

# Load .env before reading DATABASE_URL (database.py is imported before main.py runs load_dotenv)
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass
from urllib.parse import urlparse, urlunparse

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

# ── Config: Load from env with validation ─────────────────────
# Production: postgresql+asyncpg://user:pass@host:5432/dbname
# Development fallback: sqlite+aiosqlite:///./safety_monitor.db
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://safety:safety@localhost:5432/safety_monitor",
)

# Validate DATABASE_URL format
_VALID_URL_PREFIXES = (
    "sqlite+aiosqlite",
    "postgresql+asyncpg",
    "mysql+aiomysql",
)
if not DATABASE_URL or not any(DATABASE_URL.startswith(p) for p in _VALID_URL_PREFIXES):
    logger.warning(
        "DATABASE_URL format unrecognised — falling back to SQLite. "
        "For PostgreSQL set: DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname"
    )
    DATABASE_URL = "sqlite+aiosqlite:///./safety_monitor.db"

# ── Dialect helpers (SQLite vs PostgreSQL DDL differs) ────────
IS_POSTGRES = DATABASE_URL.startswith("postgresql")
_PK = "BIGSERIAL PRIMARY KEY" if IS_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
_TS = "TIMESTAMPTZ DEFAULT NOW()" if IS_POSTGRES else "DATETIME DEFAULT CURRENT_TIMESTAMP"
_BLOB = "BYTEA" if IS_POSTGRES else "BLOB"
_F = "BOOLEAN DEFAULT FALSE" if IS_POSTGRES else "BOOLEAN DEFAULT 0"
_T = "BOOLEAN DEFAULT TRUE" if IS_POSTGRES else "BOOLEAN DEFAULT 1"

# Connection pool settings (tune for production)
POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "20"))
POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))
POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "3600"))  # 1 hour


def _mask_credentials(url: str) -> str:
    """
    Mask credentials in DB URL for safe logging.

    postgres://user:pass@host/db → postgres://user:***@host/db
    SQLite URLs have no credentials — returned as-is.
    """
    try:
        parsed = urlparse(url)
        if parsed.password:
            # Rebuild netloc with masked password
            netloc = f"{parsed.username}:***"
            if parsed.hostname:
                netloc += f"@{parsed.hostname}"
            if parsed.port:
                netloc += f":{parsed.port}"
            masked = parsed._replace(netloc=netloc)
            return urlunparse(masked)
    except Exception:
        pass
    return url


def _build_connect_args(url: str) -> dict:
    """
    Return driver-specific connect_args.
    check_same_thread is SQLite-only — omitted for Postgres/MySQL.
    PostgreSQL asyncpg accepts server_settings for application_name tagging.
    """
    if url.startswith("sqlite"):
        return {
            "check_same_thread": False,
            "timeout": 30,  # Lock timeout for SQLite
        }
    if url.startswith("postgresql"):
        return {
            "server_settings": {
                "application_name": "industrial-safety-monitor",
            }
        }
    return {}


def make_engine(url: str = DATABASE_URL) -> AsyncEngine:
    """
    Create an async SQLAlchemy engine for the given database URL.

    Exposed as a factory so tests can inject an in-memory engine.

    Args:
        url: SQLAlchemy async database URL.

    Returns:
        Configured AsyncEngine instance.
    """
    # FIXED: SQLite does not support pool_size/max_overflow (uses StaticPool/NullPool)
    # Passing those kwargs to SQLite raises an error or silently ignores them.
    is_sqlite = url.startswith("sqlite")
    kwargs: dict = {
        "echo": False,
        "connect_args": _build_connect_args(url),
        "pool_pre_ping": True,
    }
    if not is_sqlite:
        kwargs.update(
            {
                "pool_size": POOL_SIZE,
                "max_overflow": MAX_OVERFLOW,
                "pool_timeout": POOL_TIMEOUT,
                "pool_recycle": POOL_RECYCLE,
            }
        )
    return create_async_engine(url, **kwargs)


def make_session_factory(eng: AsyncEngine) -> sessionmaker:
    """
    Create an async session factory bound to the given engine.

    Args:
        eng: AsyncEngine to bind sessions to.

    Returns:
        sessionmaker configured for async use.
    """
    return sessionmaker(
        eng,
        class_=AsyncSession,
        expire_on_commit=False,  # Prevent DetachedInstanceError
        autocommit=False,
        autoflush=False,
    )


# Module-level engine and session factory
engine: AsyncEngine = make_engine()
AsyncSessionLocal: sessionmaker = make_session_factory(engine)


async def init_db(eng: AsyncEngine | None = None) -> None:
    """
    Create all SQLModel tables. Call once at application startup.

    Args:
        eng: Engine to use. Defaults to module-level engine.

    Raises:
        RuntimeError: If table creation fails (bad URL, permissions, etc.)
    """
    eng = eng or engine

    # Import all table models so SQLModel.metadata knows about them before create_all
    # This must happen here (not at module level) to avoid circular imports
    import backend.models  # noqa: F401 — registers all SQLModel tables in metadata

    try:
        async with eng.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
            # ── Raw SQL tables (not managed by SQLModel ORM) ───────

            # Users table — email/password auth
            await conn.execute(
                text(f"""
                CREATE TABLE IF NOT EXISTS users (
                    id              {_PK},
                    email           VARCHAR(256) UNIQUE NOT NULL,
                    hashed_password VARCHAR(256) NOT NULL,
                    full_name       VARCHAR(128) DEFAULT '',
                    role            VARCHAR(32)  DEFAULT 'viewer',
                    org_id          VARCHAR(64)  DEFAULT 'default',
                    is_active       {_T},
                    created_at      {_TS}
                )
            """)
            )

            await conn.execute(
                text(f"""
                CREATE TABLE IF NOT EXISTS worker_profiles (
                    id             {_PK},
                    worker_id      VARCHAR(64)  UNIQUE NOT NULL,
                    full_name      VARCHAR(128) NOT NULL,
                    department     VARCHAR(64),
                    shift          VARCHAR(32),
                    role           VARCHAR(32),
                    photo_path     VARCHAR(256),
                    face_embedding {_BLOB},
                    risk_score     FLOAT    DEFAULT 0.0,
                    risk_level     VARCHAR(16) DEFAULT 'LOW',
                    hr_alerted     {_F},
                    active         {_T},
                    enrolled_at    TIMESTAMP,
                    created_at     TIMESTAMP
                )
            """)
            )

            await conn.execute(
                text(f"""
                CREATE TABLE IF NOT EXISTS camera_registry (
                    id               {_PK},
                    camera_id        VARCHAR(64) UNIQUE NOT NULL,
                    camera_name      VARCHAR(128) NOT NULL,
                    rtsp_url         VARCHAR(512) NOT NULL,
                    location         VARCHAR(128),
                    zone_id          VARCHAR(64),
                    active           {_T},
                    status           VARCHAR(32) DEFAULT 'offline',
                    fps_actual       FLOAT,
                    reconnect_count  INTEGER DEFAULT 0,
                    last_seen        TIMESTAMP,
                    updated_at       TIMESTAMP,
                    created_at       {_TS}
                )
            """)
            )

            await conn.execute(
                text(f"""
                CREATE TABLE IF NOT EXISTS camera_zones (
                    id                  {_PK},
                    zone_id             VARCHAR(64) UNIQUE NOT NULL,
                    zone_name           VARCHAR(128) NOT NULL,
                    zone_type           VARCHAR(32) NOT NULL DEFAULT 'restricted',
                    camera_id           VARCHAR(64),
                    polygon_norm        TEXT,
                    required_ppe        TEXT,
                    risk_multiplier     FLOAT DEFAULT 1.0,
                    alert_enabled       {_T},
                    dwell_threshold_s   INTEGER DEFAULT 5,
                    color_hex           VARCHAR(7) DEFAULT '#ef4444',
                    active              {_T},
                    created_at          {_TS}
                )
            """)
            )

            await conn.execute(
                text(f"""
                CREATE TABLE IF NOT EXISTS violation_events (
                    id               {_PK},
                    track_id         INTEGER NOT NULL,
                    class_name       VARCHAR(64) NOT NULL,
                    confidence       FLOAT NOT NULL,
                    zone_id          VARCHAR(64),
                    bbox_x1          FLOAT DEFAULT 0,
                    bbox_y1          FLOAT DEFAULT 0,
                    bbox_x2          FLOAT DEFAULT 0,
                    bbox_y2          FLOAT DEFAULT 0,
                    acknowledged     {_F},
                    acknowledged_by  VARCHAR(64),
                    camera_id        VARCHAR(64),
                    frame_idx        INTEGER DEFAULT 0,
                    timestamp        {_TS},
                    created_at       {_TS}
                )
            """)
            )

            await conn.execute(
                text(f"""
                CREATE TABLE IF NOT EXISTS worker_violations (
                    id           {_PK},
                    worker_id    VARCHAR(64) NOT NULL,
                    violation_id INTEGER NOT NULL,
                    timestamp    {_TS},
                    created_at   {_TS}
                )
            """)
            )

            await conn.execute(
                text(f"""
                CREATE TABLE IF NOT EXISTS agent_runs (
                    id               {_PK},
                    run_id           VARCHAR(64) UNIQUE NOT NULL,
                    violation_id     INTEGER,
                    track_id         INTEGER,
                    class_name       VARCHAR(64),
                    severity_score   FLOAT,
                    alert_level      VARCHAR(16),
                    report_id        INTEGER,
                    alert_sent       {_F},
                    compliance_delta FLOAT,
                    final_status     VARCHAR(32),
                    trace_steps      TEXT,
                    error            TEXT,
                    created_at       {_TS}
                )
            """)
            )

            await conn.execute(
                text(f"""
                CREATE TABLE IF NOT EXISTS incident_reports (
                    id                   {_PK},
                    violation_id         INTEGER,
                    run_id               VARCHAR(64),
                    track_id             INTEGER,
                    class_name           VARCHAR(64),
                    zone_id              VARCHAR(64),
                    confidence           FLOAT,
                    timestamp            {_TS},
                    incident_summary     TEXT,
                    root_cause_analysis  TEXT,
                    corrective_actions   TEXT,
                    narrative            TEXT,
                    osha_reference       VARCHAR(128),
                    severity_level       VARCHAR(16),
                    severity             VARCHAR(16),
                    actions_taken        TEXT,
                    model_used           VARCHAR(64),
                    generation_ms        FLOAT,
                    pdf_path             VARCHAR(256),
                    pdf_size_bytes       INTEGER,
                    report_json          TEXT,
                    status               VARCHAR(32) DEFAULT 'generated',
                    created_at           {_TS}
                )
            """)
            )

            await conn.execute(
                text(f"""
                CREATE TABLE IF NOT EXISTS model_deployments (
                    id                  {_PK},
                    model_name          VARCHAR(128) NOT NULL,
                    model_version       VARCHAR(32) NOT NULL,
                    stage               VARCHAR(32) DEFAULT 'production',
                    deploy_type         VARCHAR(32),
                    map50               FLOAT,
                    canary_traffic_pct  FLOAT DEFAULT 0,
                    canary_frames       INTEGER DEFAULT 0,
                    traffic_pct         FLOAT,
                    status              VARCHAR(32) DEFAULT 'active',
                    deployed_by         VARCHAR(64),
                    promoted_at         TIMESTAMP,
                    rolled_back_at      TIMESTAMP,
                    rollback_reason     TEXT,
                    notes               TEXT,
                    deployed_at         TIMESTAMP,
                    retired_at          TIMESTAMP,
                    created_at          {_TS}
                )
            """)
            )

            await conn.execute(
                text(f"""
                CREATE TABLE IF NOT EXISTS pose_hazard_events (
                    id             {_PK},
                    track_id       INTEGER NOT NULL,
                    hazard_type    VARCHAR(64) DEFAULT 'unknown',
                    severity       VARCHAR(16) DEFAULT 'MEDIUM',
                    confidence     FLOAT DEFAULT 0.0,
                    zone_id        VARCHAR(64),
                    camera_id      VARCHAR(64),
                    duration_s     FLOAT DEFAULT 0.0,
                    landmark_data  TEXT,
                    combined_alert {_F},
                    frame_idx      INTEGER DEFAULT 0,
                    timestamp      {_TS}
                )
            """)
            )

            await conn.execute(
                text(f"""
                CREATE TABLE IF NOT EXISTS proximity_alerts (
                    id               {_PK},
                    person_track_id  INTEGER NOT NULL,
                    machine_track_id INTEGER NOT NULL,
                    machine_class    VARCHAR(64),
                    pixel_distance   FLOAT,
                    real_distance_m  FLOAT,
                    alert_level      VARCHAR(16) DEFAULT 'WARNING',
                    zone_id          VARCHAR(64),
                    camera_id        VARCHAR(64),
                    frame_idx        INTEGER DEFAULT 0,
                    acknowledged     {_F},
                    timestamp        {_TS}
                )
            """)
            )

            await conn.execute(
                text(f"""
                CREATE TABLE IF NOT EXISTS fire_hazard_events (
                    id             {_PK},
                    hazard_type    VARCHAR(32) DEFAULT 'fire',
                    confidence     FLOAT NOT NULL,
                    zone_id        VARCHAR(64),
                    camera_id      VARCHAR(64),
                    bbox_x1        FLOAT,
                    bbox_y1        FLOAT,
                    bbox_x2        FLOAT,
                    bbox_y2        FLOAT,
                    frame_idx      INTEGER DEFAULT 0,
                    alert_sent     {_F},
                    acknowledged   {_F},
                    timestamp      {_TS}
                )
            """)
            )

            await conn.execute(
                text(f"""
                CREATE TABLE IF NOT EXISTS weekly_reports (
                    id               {_PK},
                    site_id          VARCHAR(64),
                    report_date      {_TS},
                    site_score       FLOAT,
                    total_violations INTEGER DEFAULT 0,
                    pdf_path         VARCHAR(256),
                    created_at       {_TS}
                )
            """)
            )
            # ── Multi-tenant tables ────────────────────────────────
            await conn.execute(
                text(f"""
                CREATE TABLE IF NOT EXISTS organizations (
                    id                      {_PK},
                    org_id                  VARCHAR(64) UNIQUE NOT NULL,
                    org_name                VARCHAR(200) NOT NULL,
                    industry_type           VARCHAR(50),
                    country                 VARCHAR(2) DEFAULT 'IN',
                    plan                    VARCHAR(20) DEFAULT 'starter',
                    plan_status             VARCHAR(20) DEFAULT 'trial',
                    trial_ends_at           TIMESTAMP,
                    max_cameras             INTEGER DEFAULT 5,
                    max_sites               INTEGER DEFAULT 1,
                    max_users               INTEGER DEFAULT 10,
                    razorpay_customer_id    VARCHAR(100),
                    razorpay_subscription_id VARCHAR(100),
                    admin_email             VARCHAR(200),
                    active                  {_T},
                    created_at              {_TS}
                )
            """)
            )

            await conn.execute(
                text(f"""
                CREATE TABLE IF NOT EXISTS industry_ppe_profiles (
                    id                  {_PK},
                    industry_type       VARCHAR(50) NOT NULL,
                    zone_type           VARCHAR(50) NOT NULL,
                    required_ppe        TEXT DEFAULT '[]',
                    risk_level          VARCHAR(16) DEFAULT 'HIGH',
                    compliance_standard VARCHAR(100) DEFAULT 'OSHA 1910.132',
                    notes               TEXT
                )
            """)
            )

            await conn.execute(
                text(f"""
                CREATE TABLE IF NOT EXISTS alert_escalations (
                    id                  {_PK},
                    violation_id        INTEGER NOT NULL,
                    org_id              VARCHAR(64),
                    site_id             VARCHAR(50),
                    level               INTEGER DEFAULT 1,
                    status              VARCHAR(20) DEFAULT 'open',
                    notified_at         TIMESTAMP,
                    acknowledged_by     VARCHAR(100),
                    acknowledged_at     TIMESTAMP,
                    escalation_reason   VARCHAR(200),
                    created_at          {_TS}
                )
            """)
            )

            await conn.execute(
                text(f"""
                CREATE TABLE IF NOT EXISTS permits_to_work (
                    id              {_PK},
                    permit_id       VARCHAR(64) UNIQUE NOT NULL,
                    org_id          VARCHAR(64),
                    site_id         VARCHAR(50),
                    zone_id         VARCHAR(64),
                    work_type       VARCHAR(100) NOT NULL,
                    worker_id       VARCHAR(64),
                    supervisor_id   VARCHAR(64),
                    status          VARCHAR(20) DEFAULT 'pending',
                    valid_from      TIMESTAMP,
                    valid_until     TIMESTAMP,
                    approved_by     VARCHAR(100),
                    approved_at     TIMESTAMP,
                    qr_code         VARCHAR(200),
                    risk_assessment TEXT,
                    created_at      {_TS}
                )
            """)
            )

            await conn.execute(
                text(f"""
                CREATE TABLE IF NOT EXISTS worker_attendance (
                    id              {_PK},
                    worker_id       VARCHAR(64) NOT NULL,
                    org_id          VARCHAR(64),
                    site_id         VARCHAR(50),
                    shift_id        INTEGER,
                    check_in        TIMESTAMP,
                    check_out       TIMESTAMP,
                    entry_method    VARCHAR(30) DEFAULT 'face_recognition',
                    entry_camera_id VARCHAR(64),
                    exit_camera_id  VARCHAR(64),
                    created_at      {_TS}
                )
            """)
            )

            await conn.execute(
                text(f"""
                CREATE TABLE IF NOT EXISTS billing_subscriptions (
                    id                      {_PK},
                    org_id                  VARCHAR(64) UNIQUE NOT NULL,
                    plan                    VARCHAR(20) NOT NULL,
                    billing_cycle           VARCHAR(10) DEFAULT 'monthly',
                    amount_paise            INTEGER DEFAULT 0,
                    currency                VARCHAR(3) DEFAULT 'INR',
                    razorpay_sub_id         VARCHAR(100),
                    status                  VARCHAR(20) DEFAULT 'trial',
                    current_period_start    TIMESTAMP,
                    current_period_end      TIMESTAMP,
                    cancelled_at            TIMESTAMP,
                    created_at              {_TS}
                )
            """)
            )

            # ── Tables previously created lazily by route handlers ──
            # Without these at startup, a fresh deploy (e.g. Render) is missing
            # them until the first relevant API call — and demo auto-seed fails.
            await conn.execute(
                text(f"""
                CREATE TABLE IF NOT EXISTS alert_recipients (
                    id              {_PK},
                    name            VARCHAR(128) NOT NULL,
                    role            VARCHAR(64),
                    email           VARCHAR(256),
                    whatsapp_number VARCHAR(32),
                    notify_critical {_T},
                    notify_high     {_T},
                    notify_medium   {_F},
                    notify_low      {_F},
                    zone_filter     TEXT,
                    active          {_T},
                    created_at      {_TS}
                )
            """)
            )
            await conn.execute(
                text(f"""
                CREATE TABLE IF NOT EXISTS alert_send_log (
                    id           {_PK},
                    recipient_id INTEGER,
                    violation_id INTEGER,
                    alert_type   VARCHAR(32),
                    zone_id      VARCHAR(64),
                    track_id     INTEGER,
                    severity     VARCHAR(16),
                    channel      VARCHAR(32),
                    status       VARCHAR(16) DEFAULT 'sent',
                    error_msg    TEXT,
                    sent_at      {_TS}
                )
            """)
            )
            await conn.execute(
                text(f"""
                CREATE TABLE IF NOT EXISTS zone_alerts (
                    id              {_PK},
                    zone_id         VARCHAR(64),
                    zone_name       VARCHAR(128),
                    alert_type      VARCHAR(64),
                    message         TEXT,
                    severity        VARCHAR(16) DEFAULT 'HIGH',
                    acknowledged    {_F},
                    acknowledged_by VARCHAR(64),
                    acknowledged_at TIMESTAMP,
                    created_at      {_TS}
                )
            """)
            )
            await conn.execute(
                text(f"""
                CREATE TABLE IF NOT EXISTS drift_results (
                    id            {_PK},
                    model_version VARCHAR(64),
                    drift_type    VARCHAR(32),
                    drift_score   FLOAT,
                    threshold     FLOAT DEFAULT 0.1,
                    is_drift      {_F},
                    details       TEXT,
                    recorded_at   {_TS}
                )
            """)
            )
            await conn.execute(
                text(f"""
                CREATE TABLE IF NOT EXISTS canary_metrics (
                    id            {_PK},
                    deployment_id INTEGER,
                    metric_name   VARCHAR(64),
                    metric_value  FLOAT,
                    recorded_at   {_TS}
                )
            """)
            )
            await conn.execute(
                text(f"""
                CREATE TABLE IF NOT EXISTS inference_stats_daily (
                    id               {_PK},
                    date             VARCHAR(12),
                    total_frames     INTEGER DEFAULT 0,
                    total_detections INTEGER DEFAULT 0,
                    avg_fps          FLOAT,
                    avg_confidence   FLOAT,
                    model_version    VARCHAR(64)
                )
            """)
            )
            await conn.execute(
                text(f"""
                CREATE TABLE IF NOT EXISTS worker_audit_log (
                    id        {_PK},
                    worker_id VARCHAR(64),
                    action    VARCHAR(64),
                    actor     VARCHAR(64),
                    details   TEXT,
                    timestamp {_TS}
                )
            """)
            )
            await conn.execute(
                text(f"""
                CREATE TABLE IF NOT EXISTS worker_compliance (
                    id            {_PK},
                    worker_id     VARCHAR(64),
                    date          VARCHAR(12),
                    ppe_score     FLOAT,
                    total_checks  INTEGER DEFAULT 0,
                    passed_checks INTEGER DEFAULT 0
                )
            """)
            )
            await conn.execute(
                text(f"""
                CREATE TABLE IF NOT EXISTS worker_risk_history (
                    id          {_PK},
                    worker_id   VARCHAR(64),
                    risk_score  FLOAT,
                    risk_level  VARCHAR(16),
                    recorded_at {_TS}
                )
            """)
            )

        logger.info("Database tables initialised")
    except Exception as exc:
        # Mask credentials before logging or raising
        masked_url = _mask_credentials(DATABASE_URL)
        logger.error("Database initialisation failed — check DATABASE_URL ({})", masked_url)
        raise RuntimeError(
            f"Database initialisation failed — " f"check DATABASE_URL ({masked_url!r}): {exc}"
        ) from exc


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields a managed async DB session.

    Behaviour:
    - Commits automatically on clean handler exit.
    - Rolls back and re-raises on any exception.
    - Session is always closed after the request completes.

    Usage:
        @router.get("/items")
        async def handler(session: AsyncSession = Depends(get_session)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            logger.warning("DB session rolled back due to exception")
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Testing utilities ─────────────────────────────────────────
async def get_test_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get a session for testing with an in-memory SQLite DB.

    Usage in tests:
        @pytest.fixture
        async def test_session():
            async with get_test_session() as session:
                yield session
    """
    test_engine = make_engine("sqlite+aiosqlite:///:memory:")
    test_session_factory = make_session_factory(test_engine)

    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with test_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
            await test_engine.dispose()
