# 🏭 SafeGuardAI — Industrial Safety Monitor

## What is this?

**Every year, thousands of factory and construction workers are injured because no one
noticed a missing helmet, an open flame near chemicals, or a worker in a danger zone —
until it was too late.** One safety officer cannot watch 20 camera feeds at once.

**SafeGuardAI turns any existing CCTV camera into a tireless AI safety inspector.** It
watches every feed in real time, flags PPE violations and hazards the instant they
happen, escalates to the right person, and auto-generates the OSHA-grade incident
paperwork — so the safety team acts in seconds instead of reviewing footage after an
accident.

**Who it's for:** plant safety managers, EHS officers, and site supervisors in
construction, steel, oil & gas, pharma, warehousing, power, shipbuilding, and mining.

**One-line value:** *Stop accidents before they happen — by catching unsafe behavior the
moment it appears, on the cameras you already own.*

---

[![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![YOLOv8](https://img.shields.io/badge/YOLOv8-ultralytics-orange)](https://github.com/ultralytics/ultralytics)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2.35-blueviolet)](https://github.com/langchain-ai/langgraph)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![CI](https://github.com/chandrukumar/industrial-safety-monitoring/actions/workflows/ci.yml/badge.svg)](https://github.com/chandrukumar/industrial-safety-monitoring/actions/workflows/ci.yml)

---

## 📸 Demo

> **[Add GIF/screenshot here — record with OBS or Loom]**
> Suggested: 30-second screen recording of Landing → Login → Dashboard → violation trigger → escalation flow.
> Full system walkthrough in [`ARCHITECTURE_NOTES.md`](ARCHITECTURE_NOTES.md).

---

## ✨ Key Features

- **Real-time PPE detection** — YOLOv8 detects missing helmet, vest, hardhat, gloves, and goggles across live RTSP/webcam streams
- **ByteTrack multi-person tracking** — persistent worker track IDs across frames, even through occlusions
- **LangGraph autonomous agent** — 8-node StateGraph: detect → check history → score severity → decide alert level → generate report → send alert → log to DB → update compliance
- **MediaPipe pose hazard detection** — identifies dangerous bending, fatigue posture, fall events, and restricted zone reaching in parallel with PPE model
- **Worker identity & risk scoring** — DeepFace face enrollment + 7-day recency-weighted rolling risk score per worker with HR escalation
- **RAG safety chatbot** — LangChain + ChromaDB retrieval over your own safety procedure documents
- **MLOps with canary deployment** — MLflow model registry, hash-based traffic splitting between production and canary model, automated evaluation and rollback
- **SHAP explainability** — per-detection saliency maps showing exactly why a violation was flagged
- **Multi-site & shift management** — register multiple physical locations, manage shifts, track per-site compliance
- **Production-ready** — 60+ REST endpoints across 30 routers, Bearer token auth, 4-role RBAC, multi-tenant SaaS, OSHA/ISO 45001 immutable audit log, Docker + Railway deploy configs included

---

## 🛠️ Tech Stack

| Category | Technology | Purpose |
|---|---|---|
| Detection | YOLOv8 (ultralytics 8.2.18) | PPE violation classification on live frames |
| Tracking | ByteTrack (supervision 0.21) | Multi-person track ID persistence |
| Pose Analysis | MediaPipe 0.10 | Body keypoint physical hazard detection |
| Face Identity | DeepFace 0.0.93 | Worker enrollment & 1:N recognition |
| AI Agent | LangGraph 0.2.35 | Stateful 8-node autonomous safety workflow |
| LLM | Ollama / OpenAI (configurable) | Severity scoring & incident narrative generation |
| RAG | LangChain 0.2 + ChromaDB 0.5 | Safety document Q&A chatbot |
| Explainability | SHAP 0.45 | Detection saliency maps |
| MLOps | MLflow | Model registry + canary deployment traffic splitting |
| API | FastAPI 0.111 + Pydantic v2 | 39 REST endpoints with OpenAPI docs |
| ORM | SQLModel + aiosqlite / PostgreSQL | Async database layer |
| Auth | Bearer token + RBAC | 4 roles: viewer / operator / manager / admin |
| Frontend | React 19 + Vite 8 | 12-tab responsive dashboard UI |
| Deploy | Docker Compose + Railway | Container + one-click cloud deploy |

---

## 🏗️ Architecture

```
industrial-safety-monitoring/
│
├── backend/
│   ├── main.py               # FastAPI app factory, CORS, Bearer auth middleware
│   ├── pipeline.py           # CV inference worker thread (never blocks event loop)
│   ├── models.py             # SQLModel ORM + Pydantic v2 schemas
│   ├── database.py           # Async SQLAlchemy engine, session factory, init_db
│   │
│   ├── agent/                # LangGraph autonomous safety agent
│   │   ├── graph.py          # StateGraph + conditional routing logic
│   │   ├── nodes.py          # 8 individual agent node functions
│   │   ├── state.py          # AgentState TypedDict definition
│   │   └── tools.py          # DB query tools used by nodes
│   │
│   ├── identity/             # Worker identity subsystem
│   │   ├── face_recognizer.py    # DeepFace enrollment + matching
│   │   ├── risk_scorer.py        # 7-day recency-weighted risk score
│   │   └── face_blurrer.py       # Privacy: blur faces before storage
│   │
│   ├── mlops/                # MLOps pipeline
│   │   ├── model_registry.py     # MLflow model version management
│   │   ├── canary_router.py      # Hash-based traffic splitting
│   │   └── canary_evaluator.py   # Automated canary pass/fail logic
│   │
│   ├── alerts/               # Fire detection engine + alert dispatcher
│   ├── cameras/              # RTSP stream manager + multi-camera registry
│   ├── rag/                  # ChromaDB + LangChain knowledge base
│   ├── reports/              # Weekly compliance PDF report generator
│   ├── webhooks/             # Outbound webhook dispatcher (Slack/Teams/JIRA)
│   └── routes/               # 24 FastAPI route files → 39 endpoints total
│
├── frontend/
│   └── src/components/       # 26 React components (12-tab dashboard)
│
├── docker/                   # Dockerfile.backend + Dockerfile.frontend
├── docker-compose.yml        # Full-stack local dev
└── railway.toml              # Railway.app one-click cloud deploy config
```

---

## ⚡ Quick Start

### 1. Clone & Install Backend

```bash
git clone https://github.com/chandrukumar/industrial-safety-monitoring
cd industrial-safety-monitoring

# Create virtualenv
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux / Mac

pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` — minimum required:

```env
API_KEY=your-secret-key-here
DEMO_MODE=true              # true = no camera needed (great for portfolio)
DATABASE_URL=sqlite+aiosqlite:///./safety_monitor.db
```

### 3. Run Backend

```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
# API docs: http://localhost:8000/docs
```

### 4. Run Frontend

```bash
cd frontend
npm install
npm run dev
# Dashboard: http://localhost:5173
```

### One-click start (Windows)

```bash
start-dev.bat
```

---

## 🔌 API Endpoints

All endpoints require `Authorization: Bearer <API_KEY>` header (except `/health`).

| Method | Path | Description |
|---|---|---|
| GET | `/health` | System health + pipeline status (public) |
| GET | `/detections` | Violation event log with filters |
| GET | `/detections/stats` | Violation counts by class and zone |
| GET | `/heatmap` | Violation density heatmap image (PNG or JSON) |
| GET | `/shap/{track_id}` | SHAP saliency explanation for a detection |
| GET/POST | `/workers` | Worker profiles list + create |
| GET | `/workers/dashboard/risk` | Risk dashboard — top offenders, HR alerts |
| GET | `/workers/{id}/risk` | Per-worker 7-day rolling risk score |
| GET/POST | `/cameras` | Camera registry CRUD + RTSP management |
| GET/POST | `/zones` | Zone definitions + PPE requirements per zone |
| GET/POST | `/webhooks` | Outbound webhook CRUD + delivery test |
| POST | `/webhooks/{id}/test` | Fire a test payload to verify webhook |
| GET | `/mlops/models` | All registered model versions (MLflow) |
| GET | `/mlops/canary/status` | Active canary deployment + traffic split |
| GET | `/agent/status` | LangGraph agent config + enabled state |
| GET | `/agent/runs` | Agent run history with trace steps |
| GET | `/export/violations.csv` | Download violation log as CSV |
| GET | `/export/workers.csv` | Download worker compliance data as CSV |
| GET | `/audit` | OSHA/ISO 45001 immutable audit log |
| GET | `/chat` | RAG chatbot query over safety documents |
| GET/POST | `/sites` | Multi-site registration and management |
| GET/POST | `/shifts` | Shift schedule management |
| GET | `/reports` | Incident report list |
| GET | `/reports/stats/summary` | Report statistics |

Full interactive docs: **`http://localhost:8000/docs`**

---

## 🌍 Environment Variables

| Variable | Default | Description |
|---|---|---|
| `API_KEY` | `""` | Bearer token for all API endpoints |
| `SECRET_KEY` | — | JWT / session signing key |
| `DATABASE_URL` | `sqlite+aiosqlite:///./safety_monitor.db` | DB connection string |
| `MODEL_PATH` | `models/best.pt` | Path to YOLOv8 weights file |
| `VIDEO_SOURCE` | `0` | Webcam index or `rtsp://...` URL |
| `DEVICE` | `cpu` | Inference device: `cpu` or `cuda` |
| `CONFIDENCE_THRESHOLD` | `0.35` | YOLOv8 detection confidence threshold |
| `IOU_THRESHOLD` | `0.45` | Non-max suppression IOU threshold |
| `DEMO_MODE` | `false` | `true` = serve synthetic data (no camera required) |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed frontend origins |
| `RBAC_ENABLED` | `false` | Enable role-based access control |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | LLM endpoint for agent severity scoring |
| `MLFLOW_TRACKING_URI` | `sqlite:///mlflow/mlflow.db` | MLflow backend store |
| `CONTACT_EMAIL` | — | Shown in OpenAPI docs contact info |

See `.env.example` for the full list.

---

## 🐳 Docker

```bash
# Full stack (backend + frontend + DB)
docker-compose up -d

# Backend only
docker build -f docker/Dockerfile.backend -t safety-backend .
docker run -p 8000:8000 --env-file .env safety-backend
```

---

## ☁️ Deploy to Railway

```bash
# 1. Push to GitHub
git push origin main

# 2. Go to railway.app → New Project → Deploy from GitHub repo
# 3. Add a PostgreSQL plugin
# 4. Set env vars in Railway dashboard (API_KEY, DATABASE_URL, etc.)
# 5. Railway auto-builds from docker/Dockerfile.backend
```

`railway.toml` is already configured — zero extra setup needed.

---

## 📁 Database Schema (key tables)

| Table | Purpose |
|---|---|
| `violation_events` | Every PPE violation detected (class, zone, confidence, track_id) |
| `worker_profiles` | Worker identity, face embedding, risk score, HR alert status |
| `worker_violations` | Junction: worker ↔ violation event |
| `camera_registry` | RTSP cameras, status, fps, last seen |
| `camera_zones` | Zone polygons + required PPE per zone |
| `agent_runs` | LangGraph agent execution history + trace steps |
| `incident_reports` | Auto-generated incident reports with narrative |
| `audit_log` | Immutable OSHA/ISO 45001 compliance audit trail |
| `webhooks` | Registered outbound webhooks (Slack / Teams / JIRA) |
| `model_deployments` | MLflow canary deployment tracking |
| `sites` | Multi-site physical location registry |
| `shifts` | Shift schedules per site |

---

## 🗺️ Roadmap

- [x] YOLOv8 PPE detection pipeline
- [x] ByteTrack multi-person tracking
- [x] LangGraph 8-node autonomous safety agent
- [x] MediaPipe body-pose hazard detection
- [x] DeepFace worker identity + face enrollment
- [x] SHAP explainability endpoint
- [x] MLflow model registry + canary deployment
- [x] RAG safety chatbot (LangChain + ChromaDB)
- [x] 39 REST API endpoints + React dashboard
- [x] OSHA/ISO 45001 audit log
- [x] Docker + Railway deploy configs
- [ ] Train domain-specific YOLOv8 model on manufacturing dataset
- [ ] Enable Ollama LLM for live AI-written incident narratives
- [ ] PostgreSQL + Redis for horizontal scaling
- [ ] Mobile supervisor app (React Native)

---

## 🧪 Testing

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run full test suite (116 tests)
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=backend --cov-report=term-missing
```

**116 tests, all passing.** Coverage areas:
- ✅ Authentication & RBAC (401/403 regression tests)
- ✅ Health + liveness/readiness probes (DB dependency check)
- ✅ Worker profiles & risk scoring (route ordering regression)
- ✅ Camera registry (rtsp:// Pydantic regression)
- ✅ Zones (NULL zone_type regression)
- ✅ MLOps endpoints (asyncio import regression)
- ✅ Reports & audit log + CSV/JSON export
- ✅ Enterprise: organizations, billing, escalation, permits, attendance, industry PPE (47 tests)
- ✅ Pydantic v2 model validation

---

## 🗄️ Database Migrations (Alembic)

All schema changes are managed through versioned Alembic migrations.
**Never edit the DB directly.**

```bash
# Apply all pending migrations (first-time setup)
alembic upgrade head

# Check current migration version
alembic current

# Create a new migration after changing models.py
alembic revision --autogenerate -m "describe your change"

# Rollback last migration
alembic downgrade -1

# Preview SQL without applying
alembic upgrade head --sql
```

---

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for full developer guide including:
- Local setup instructions
- Commit conventions (Conventional Commits)
- How to add new API endpoints
- Alembic migration workflow
- Code style (ruff + ESLint)

Quick start:
1. Fork the repository
2. Create a feature branch: `git checkout -b feat/your-feature`
3. Make changes + write tests
4. Run: `pytest tests/ -q && ruff check .`
5. Commit: `git commit -m 'feat(scope): description'`
6. Open a PR using the [PR template](.github/PULL_REQUEST_TEMPLATE.md)

---

## 📄 License

MIT © Chandrukumar S — see [LICENSE](LICENSE) for details.

---

## 📧 Contact

**Chandrukumar S**  
📧 kumarchandru646@gmail.com  
🔗 [linkedin.com/in/chandrukumar-s-69a673208](https://linkedin.com/in/chandrukumar-s-69a673208)  
🐙 [github.com/chandrukumar](https://github.com/chandrukumar)

---

> ⭐ If this project helped you, please star the repository — it helps others find it.

**Built with ❤️ for Industrial Safety**
