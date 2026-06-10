# Portfolio Note

## On the commit history

This repository's git history is intentionally compact (a small number of large commits)
because it was built **iteratively in long pair-programming sessions with Claude Code**,
where work was committed in consolidated milestones rather than micro-commits. The *logical*
development phases — which is what matters for understanding how it was built — were:

### Phase 1 — Core Vision Pipeline
YOLOv8 PPE detection + ByteTrack multi-person tracking, the inference pipeline running in a
background thread, and the WebSocket frame stream to the dashboard.

### Phase 2 — Persistence & API
SQLModel data layer, FastAPI routers for detections/zones/cameras/workers, Bearer-token
auth, and the React dashboard shell.

### Phase 3 — Intelligence Layer
LangGraph severity-scoring agent, RAG safety chatbot (ChromaDB), SHAP explainability, and
the multi-provider LLM fallback chain (Groq → OpenRouter → OpenAI → Ollama → template).

### Phase 4 — Safety Workflows
Fire/smoke detection, human-machine proximity alerts, pose-hazard detection, alert
configuration, and incident report generation.

### Phase 5 — Enterprise SaaS
Multi-tenant organizations + `X-Org-ID` middleware, Razorpay billing, industry PPE
profiles (8 industries), L1→L4 alert escalation with APScheduler, digital permit-to-work,
and worker attendance/muster.

### Phase 6 — MLOps & Compliance
MLflow model registry, canary deployment with traffic splitting + auto-rollback, drift
detection, immutable OSHA/ISO 45001 audit log, and CSV/JSON compliance export.

### Phase 7 — Client-Facing Polish
Marketing landing page, gated login flow, unique Hi-Vis Amber theme, full demo-data
seeder (21 tables), and a 15-level production hardening audit.

---

## What to look at first

- **`ARCHITECTURE_NOTES.md`** — the system walkthrough.
- **`DECISIONS.md`** — the five key technology choices and trade-offs.
- **`backend/main.py`** — app wiring, middleware order, lifespan, 30 routers.
- **`backend/llm/manager.py`** — the resilient multi-provider LLM chain.
- **`scripts/demo_seed.py`** — one command (`python scripts/demo_seed.py --reset`) brings
  the whole platform to life with realistic data across all 8 industries.

## Verification status
- Backend: **113/113 tests passing**
- API: **60/60 endpoints returning 2xx** against seeded demo data
- Frontend: production build passes; all 18 panels verified in a live preview walkthrough
