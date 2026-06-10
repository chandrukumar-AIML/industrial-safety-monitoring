# Architecture Decision Records

The five most consequential technology choices in SafeGuardAI, and *why* each was made.

---

## 1. FastAPI + SQLModel (async) over Django / Flask

**Decision:** Build the backend on FastAPI with SQLModel (Pydantic + SQLAlchemy) and an
async stack (`aiosqlite` in dev, `asyncpg` in prod).

**Why:**
- The workload is I/O-bound (DB writes per detection, WebSocket frame streaming, outbound
  LLM/webhook calls). Async lets one worker handle many concurrent connections without
  thread-per-request overhead.
- SQLModel gives one class that is *both* the Pydantic request/response schema and the ORM
  table — less duplication, validation for free at the API boundary.
- FastAPI auto-generates OpenAPI docs, which doubles as living API documentation for the
  60+ endpoints.

**Trade-off:** Async SQLAlchemy is less mature than Django's ORM and has sharper edges
(greenlet errors, no lazy loading). Accepted for the concurrency win.

---

## 2. Multi-provider LLM fallback chain over a single hosted model

**Decision:** `LLMManager` tries Groq → OpenRouter → OpenAI → Ollama → static template, in
order, and never raises.

**Why:**
- Incident-report generation must *never* block a safety alert. If every provider is down,
  the template path still produces a usable report.
- Groq's free tier (14,400 req/day) makes the demo and early customers cost ₹0; paid
  providers only engage if free ones fail.
- Decouples the product from any one vendor's pricing or uptime.

**Trade-off:** Output quality varies across providers. Accepted because resilience >
stylistic consistency for compliance paperwork.

---

## 3. SQLite in dev, PostgreSQL in prod — same code path

**Decision:** One `DATABASE_URL` switch. SQLite (`aiosqlite`) locally, Postgres
(`asyncpg`) in production, with connection pooling only enabled for Postgres.

**Why:**
- Zero-setup local development and CI (in-memory SQLite) — contributors clone and run with
  no database server.
- Postgres in production for real concurrency, connection pooling (size 10, overflow 20),
  and `pool_pre_ping` to survive dropped connections.

**Trade-off:** Must avoid Postgres-only SQL (`ILIKE`, `NOW()`, `INTERVAL`). A few
dialect-specific bugs were fixed during audit; raw SQL is kept ANSI-compatible.

---

## 4. Tab-state SPA with a router gate, not server-rendered pages

**Decision:** React SPA. Public routes (`/`, `/login`) are real React Router routes; the
authenticated app (`/app`) is gated behind a `RequireAuth` wrapper, with panels switched
via in-memory tab state.

**Why:**
- The dashboard is a long-lived, real-time surface (WebSocket video, polling panels).
  Full-page reloads would tear down the stream connection.
- A marketing landing page + login gate makes it a client-facing product, not a dev tool.

**Trade-off:** Deep-linking to a specific panel isn't supported (tab is component state,
not URL). Acceptable for a single-operator console; noted as a v2 item.

---

## 5. Background scheduler (APScheduler) in-process over Celery + broker

**Decision:** Alert escalation runs on an in-process `AsyncIOScheduler` job every 60s, not
a Celery worker with Redis/RabbitMQ.

**Why:**
- The only recurring job is escalation sweeps — lightweight, idempotent, DB-backed. A full
  Celery + broker deployment would triple the infra for one cron-like task.
- Keeps the deployment to two containers (API + DB) for early customers.

**Trade-off:** The scheduler is tied to the API process and doesn't scale horizontally —
running N API replicas would run the job N times. Mitigated today by `max_instances=1` +
`coalesce`; the documented v2 fix is to move to Celery beat or a leader-elected job when
multi-replica is needed.
