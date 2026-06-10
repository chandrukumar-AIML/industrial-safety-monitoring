# Changelog

All notable changes to the **Industrial Safety Monitor** are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Planned
- Train domain-specific YOLOv8 model on manufacturing PPE dataset (Colab notebook)
- PostgreSQL + Redis for horizontal scaling (production deploy)
- Mobile supervisor app (React Native)
- WhatsApp / Telegram real-time alert delivery
- Face recognition attendance (DeepFace → real-time check-in)

---

## [1.3.0] — 2026-06-08

### Added (Enterprise SaaS — 100% Industry-Ready)

#### LLM Manager (Multi-Provider Fallback Chain)
- **`backend/llm/manager.py`** — Enterprise LLM Manager: Groq → OpenRouter → OpenAI → Ollama → Template
- Groq API FREE tier (14,400 req/day) — `llama-3.1-8b-instant` — zero cost on Render
- OpenRouter free fallback — `meta-llama/llama-3-8b-instruct:free`
- Always-works template fallback (no API key needed in dev/test)
- `generate()`, `score_severity()`, `generate_incident_narrative()`, `answer_safety_question()` methods
- Wired into `backend/reports/generator.py` — replaces Ollama-only with full fallback chain
- Wired into `backend/rag/chatbot.py` — replaces `OllamaLLM` with `LLMManager`

#### Multi-Tenant Architecture
- **`backend/models.py`** — Added `Organization`, `IndustryPPEProfile`, `AlertEscalation`, `PermitToWork`, `WorkerAttendance`, `BillingSubscription` SQLModel tables
- **`backend/middleware/tenant.py`** — `TenantMiddleware`: resolves `X-Org-ID` header → `request.state.org_id`
- **`backend/routes/organizations_route.py`** — 7 endpoints: create, list, get, update, usage, activate, suspend
- `X-Org-ID` header added to CORS allowed headers

#### Subscription Billing (Razorpay India-First)
- **`backend/routes/billing_route.py`** — 5 endpoints: plans, get subscription, subscribe, Razorpay webhook, cancel
- Plans: Starter ₹4,999/mo (5 cams), Growth ₹14,999/mo (25 cams), Enterprise ₹39,999/mo (unlimited)
- Razorpay webhook handler: `subscription.activated`, `subscription.charged`, `subscription.cancelled`, `payment.failed`
- Graceful fallback when `RAZORPAY_KEY_ID` not set (demo/test mode)

#### Industry PPE Profiles (8 Industries, 23 Zone-Type Configs)
- **`backend/routes/industry_ppe_route.py`** — 5 endpoints: seed, list, get by industry, create custom, compliance check
- Pre-seeded: Construction, Steel/Manufacturing, Oil & Gas, Pharma, Warehouse, Power Plant, Shipbuilding, Mining
- Each industry + zone type maps to required PPE list + compliance standard (IS/OSHA/DGMS/CEA/WHO GMP)
- `GET /industry-ppe/check?industry_type=construction&zone_type=general&detected_class=no+hardhat` → `is_violation: true/false`

#### Alert Escalation Matrix (L1 → L4)
- **`backend/routes/escalation_route.py`** — 5 endpoints: open alerts, status, acknowledge, stats, manual trigger
- L1: Supervisor (2 min), L2: Safety Officer (10 min), L3: Plant Head (30 min), L4: Emergency (immediate)
- Background `run_escalation_check()` function for APScheduler (60-second interval)
- Auto-escalates unacknowledged alerts, logs escalation reason

#### Digital Permit-to-Work System
- **`backend/routes/permit_route.py`** — 7 endpoints: request, list, validate (QR), approve, cancel, close, list expired
- Supports: hot_work, confined_space, electrical (LOTO), height_work, chemical, excavation, radiation, cold_work
- QR code generation (SHA-256 tamper detection), time-bounded validity
- `GET /permits/validate/{permit_id}?zone_id=furnace-1` → `allowed: true/false` with reason

#### Attendance & Headcount
- **`backend/routes/attendance_route.py`** — 7 endpoints: check-in, check-out, headcount, active workers, today, history, muster drill
- Methods: face_recognition | manual | qr
- Real-time `GET /attendance/headcount` → on-site count per site
- `POST /attendance/muster` → emergency evacuation headcount snapshot
- Worker hours calculation (check-out − check-in)

#### Database
- **`backend/database.py`** — Added 6 new `CREATE TABLE IF NOT EXISTS` blocks for all enterprise tables
- **`backend/main.py`** — Registered 6 new enterprise routers (36 new endpoints total)
- OpenAPI tags expanded with enterprise feature descriptions

---

## [1.2.0] — 2025-06-08

### Added (Enterprise Upgrade)
- **Alembic migrations** — replaced manual ALTER TABLE scripts with proper versioned migrations (`alembic/versions/0001_initial_schema.py`)
- **Database indexes** — added 20+ indexes on `timestamp`, `worker_id`, `zone_id`, `track_id`, `class_name` columns for query performance
- **Full test suite** (`tests/`) — 8 test modules, 40+ test cases covering auth, workers, cameras, detections, zones, MLOps, reports, audit
- **API rate limiting** — `slowapi` middleware: 60 req/min default, 20 for inference, 5 for exports, 429 with Retry-After header
- **ErrorBoundary component** — per-panel React error isolation with error ID, dev stack trace, retry button
- **CI pipeline upgrade** — added frontend lint job, security scan (pip-audit), pytest coverage reporting, Codecov integration
- **GitHub PR template** — structured PR checklist with testing requirements
- **GitHub Issue templates** — bug report + feature request templates
- **CONTRIBUTING.md** — developer onboarding guide with commit conventions

### Fixed
- `asyncio.Lock()` in `canary_router.py` without `import asyncio` → added import
- `HttpUrl` Pydantic v2 rejecting `rtsp://` scheme → changed `rtsp_url` to `str`
- `WorkerRiskOut(**risk)` Pydantic v2 star-unpack failure → explicit `.model_dump()`
- FastAPI route ordering: `/workers/dashboard/risk` swallowed by `/{worker_id}/risk`
- `session.exec()` vs `session.execute()` in reports stats endpoint → SQLAlchemy correct method
- `new URL('/api/audit')` browser TypeError for relative URLs → string concatenation
- `hazards.filter is not a function` — PoseHazardPanel received 401 JSON object → `Array.isArray()` guard

---

## [1.1.0] — 2025-06-01

### Added
- **LangGraph autonomous agent** — 8-node StateGraph (detect → check history → score severity → decide alert level → generate report → send alert → log → update compliance)
- **MediaPipe pose hazard detection** — dangerous bending, fatigue posture, fall, restricted zone reaching
- **DeepFace worker identity** — face enrollment + 1:N recognition + privacy blurring
- **SHAP explainability endpoint** — per-detection saliency map (`GET /shap/{track_id}`)
- **MLflow canary deployment** — hash-based traffic splitting, automated pass/fail evaluation
- **ChromaDB RAG chatbot** — LangChain retrieval over safety procedure documents
- **Multi-site management** — sites, shifts, per-site compliance tracking
- **Webhooks** — Slack/Teams/JIRA outbound webhook with HMAC signing
- **Audit log** — OSHA/ISO 45001 immutable event log with actor, action, resource fields
- **CSV export** — violations and worker data export
- **Demo mode** — synthetic data for portfolio/trade show (no camera required)
- **4-role RBAC** — viewer / operator / manager / admin with Bearer token auth

### Fixed
- SQLite `NOW()` → `CURRENT_TIMESTAMP` (SQLite-compatible)
- SQLite `active=TRUE` → `active=1`
- SQLite `FILTER(WHERE...)` → `CASE WHEN`
- Multiple missing columns added via fix scripts (now superseded by Alembic)

---

## [1.0.0] — 2025-05-15

### Added — Initial Release
- **YOLOv8 PPE detection** — real-time helmet, vest, hardhat, gloves, goggles detection
- **ByteTrack multi-person tracking** — persistent track IDs across frames via supervision
- **FastAPI REST API** — 39 endpoints, Bearer token auth, OpenAPI docs
- **React dashboard** — 12 tabs: Live Feed, Violations, Heatmap, Workers, Cameras, Zones, Pose, Proximity, Fire, Agent, MLOps, Reports
- **SQLModel ORM** — async SQLite with aiosqlite (PostgreSQL in production)
- **Docker Compose** — full-stack local dev setup
- **Railway deploy config** — `railway.toml` for one-click cloud deploy
- **WebSocket stream** — annotated video frames at `/stream`

---

[Unreleased]: https://github.com/chandrukumar/industrial-safety-monitoring/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/chandrukumar/industrial-safety-monitoring/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/chandrukumar/industrial-safety-monitoring/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/chandrukumar/industrial-safety-monitoring/releases/tag/v1.0.0
