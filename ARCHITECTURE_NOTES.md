# Architecture Notes — SafeGuardAI

> The document to walk an interviewer through when they say *"explain your architecture."*

---

## 1. System Overview

SafeGuardAI is a real-time industrial safety monitoring platform. It ingests video from
existing CCTV/RTSP cameras, runs YOLOv8-based computer vision to detect PPE violations
(missing helmet, vest, gloves, etc.), fire/smoke, human-machine proximity, and unsafe
poses, then drives an automated response: severity scoring, multi-level alert escalation
(L1 supervisor → L4 emergency), AI-generated OSHA incident reports, and a compliance audit
trail. It is delivered as a multi-tenant SaaS with a React dashboard, organization
management, and India-first (Razorpay) billing, covering 8 industries.

---

## 2. Why Each Major Technology Was Chosen

- **FastAPI (async)** — I/O-bound workload (DB writes per detection, WebSocket streaming,
  outbound LLM/webhook calls); async handles high connection concurrency per worker.
- **SQLModel** — single class is both Pydantic schema and ORM table; validation at the API
  boundary for free across 60+ endpoints.
- **YOLOv8 + ByteTrack (Ultralytics)** — best-in-class real-time object detection with
  persistent multi-person tracking, so a worker keeps one track ID across frames.
- **PostgreSQL (prod) / SQLite (dev)** — one `DATABASE_URL` switch; zero-setup local dev,
  pooled Postgres in production.
- **LLM fallback chain (Groq→OpenRouter→OpenAI→Ollama→template)** — incident reporting must
  never block on a vendor outage; free tiers keep cost at ₹0 for early use.
- **APScheduler (in-process)** — one lightweight recurring job (escalation sweep); avoids a
  Celery + broker deployment for a cron-like task.
- **React + Vite + Tailwind** — fast SPA for a real-time console; Hi-Vis Amber theme
  differentiates from blue-themed competitors.
- **slowapi** — per-route rate limiting on a public-facing API.

---

## 3. Data Flow — One Request, HTTP to Response

Example: a client dashboard loads the violation log.

1. **Browser** issues `GET /api/v1/detections?limit=50` (via the Vite dev proxy, which
   rewrites `/api` → backend root and injects the `Authorization: Bearer` header).
2. **CORS middleware** validates the origin against the explicit allow-list.
3. **TenantMiddleware** reads `X-Org-ID` and sets `request.state.org_id` for tenant
   scoping.
4. **Auth middleware** checks the Bearer token against `API_KEY` (health/docs/stream are
   excluded). Invalid → `401/403` JSON, never a traceback.
5. **slowapi** checks the per-client rate limit for the route.
6. **Route handler** (`detections.py`) validates query params via FastAPI typing, then
   calls into the DB layer using a **pooled async session** (`AsyncSessionLocal`).
7. **PostgreSQL** returns rows; SQLModel serializes them through the response model.
8. Handler returns the list; FastAPI encodes JSON; middleware chain unwinds; response goes
   back through the proxy to the browser.

Real-time path differs: the **inference pipeline** runs in a dedicated background thread,
pushing annotated frames + detections to `app_state`, which the **WebSocket `/stream`**
endpoint broadcasts to connected dashboards. Detections are persisted asynchronously and
can trigger the escalation job.

---

## 4. Scale Bottleneck — What Breaks First at 10×

**First to break: the single-process inference pipeline + in-process scheduler.**

- The CV pipeline runs in one background thread per API process. At 10× cameras it
  saturates CPU/GPU on one box. **Fix:** decouple inference into a pool of GPU workers that
  read from a frame queue (Redis Stream / Kafka) and write detections back — the API
  becomes a thin stateless layer.
- The APScheduler escalation job is bound to the API process; running multiple API replicas
  would execute it N times. **Fix:** move to Celery beat or a leader-elected/locked job.
- SQLite would be long gone by then; **Postgres with the configured pool (10 + 20
  overflow)** handles the API tier, but the per-detection write rate becomes the next
  ceiling — **fix** with batched writes and a time-series table partitioned by day.

**Second: WebSocket fan-out** — broadcasting frames to many dashboards from one process.
**Fix:** a pub/sub layer (Redis) so any API replica can serve any client.

---

## 5. Known Trade-offs (sacrificed for speed of development)

- **In-process scheduler, not Celery** — simpler deploy now, doesn't scale horizontally.
- **Tab-state navigation, not URL routes** for dashboard panels — no deep-linking.
- **Raw SQL in a few hot endpoints** — fast to write, but had to be made ANSI-compatible
  by hand (Postgres-only syntax caused bugs that the audit fixed).
- **API-key auth, not full OAuth/JWT user accounts** — fine for a single-operator console
  and demos; real per-user identity is a v2 item.
- **Model accuracy** — ships with a base YOLO weight; production accuracy needs
  fine-tuning on a labeled Indian PPE dataset.

---

## 6. What Would Be Different in v2

1. **Decoupled inference workers** — pull frames from a queue, scale GPU independently of
   the API tier; API becomes fully stateless and horizontally scalable.
2. **Real identity & RBAC** — JWT user accounts with refresh tokens and per-org user
   management, replacing the single shared API key.
3. **URL-routed dashboard + per-role views** — deep-linkable panels and a simplified
   "supervisor" view separate from the full admin console, so a floor supervisor isn't
   shown MLOps and billing.
