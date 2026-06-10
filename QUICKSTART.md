# 🛡️ Industrial Safety Monitor — Quick Start

AI-powered real-time PPE detection, fire alerts, autonomous incident reporting, and MLOps — built with YOLOv8, LangGraph, FastAPI, and React.

---

## ⚡ Fastest Way: Docker (5 minutes, no setup)

```bash
# 1. Clone
git clone https://github.com/YOUR_USERNAME/industrial-safety-monitoring.git
cd industrial-safety-monitoring

# 2. Configure (generate secrets)
cp .env.example .env
# On Linux/Mac:
sed -i "s/API_KEY=/API_KEY=$(openssl rand -hex 32)/" .env
sed -i "s/SECRET_KEY=/SECRET_KEY=$(openssl rand -hex 32)/" .env
# On Windows PowerShell:
# (Get-Content .env) -replace 'API_KEY=','API_KEY=YOUR_KEY_HERE' | Set-Content .env

# 3. Enable demo mode (no camera needed for portfolio/demo)
echo "DEMO_MODE=true" >> .env

# 4. Start everything
docker compose up -d

# 5. Open the dashboard
start http://localhost          # Windows
open http://localhost           # Mac
```

**That's it.** Dashboard at `http://localhost`, API docs at `http://localhost:8000/docs`.

---

## 🎭 Demo Mode (Portfolio / Trade Show)

No camera or GPU required. Shows fully synthetic realistic data.

```bash
# In .env:
DEMO_MODE=true

# Then call the demo endpoint:
curl http://localhost:8000/demo/full-dataset
```

All dashboard panels populate automatically from synthetic data.

---

## 🔧 Manual Setup (Local Dev, No Docker)

### Prerequisites
- Python 3.11+
- Node.js 20+
- PostgreSQL 16 (or use SQLite for dev — see below)

### Backend
```bash
# Create virtualenv
python -m venv .venv
source .venv/bin/activate        # Linux/Mac
.venv\Scripts\activate           # Windows

# Install deps
pip install -r requirements.txt

# Download YOLO model weights
python download_model.py

# Start PostgreSQL (or skip — use SQLite for dev)
# For SQLite: change DATABASE_URL in .env to:
# DATABASE_URL=sqlite+aiosqlite:///./safety_monitor.db

# Run backend
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:5173
```

---

## 🗄️ Database

**Production (default):** PostgreSQL 16
```
DATABASE_URL=postgresql+asyncpg://safety:YOUR_PASS@localhost:5432/safety_monitor
```

**Local dev (no PostgreSQL needed):**
```
DATABASE_URL=sqlite+aiosqlite:///./safety_monitor.db
```

Tables are created automatically on first startup via SQLModel's `create_all()`.

---

## 📡 Key Services

| Service | URL | Purpose |
|---------|-----|---------|
| Dashboard | http://localhost | Main safety monitoring UI |
| API Docs | http://localhost:8000/docs | Full Swagger UI |
| MLflow | http://localhost:5000 | Model experiments & registry |
| pgAdmin | http://localhost:5050 | PostgreSQL web UI (dev only) |

---

## 🔑 Environment Variables (Critical)

| Variable | Required | Description |
|----------|----------|-------------|
| `API_KEY` | ✅ Yes | Bearer token for API auth |
| `SECRET_KEY` | ✅ Yes | Session / signing key |
| `DATABASE_URL` | ✅ Yes | PostgreSQL or SQLite URL |
| `DEMO_MODE` | Optional | `true` = synthetic data, no camera needed |
| `VIDEO_SOURCE` | Optional | `0`=webcam, `rtsp://...`=IP camera |
| `OPENAI_API_KEY` | Optional | GPT-4o fallback (Ollama used by default) |
| `TWILIO_*` | Optional | WhatsApp violation alerts |
| `SMTP_*` | Optional | Email violation alerts |
| `RBAC_ENABLED` | Optional | `true` to enforce API key roles |
| `ADMIN_API_KEY` | Optional | Master admin key (when RBAC enabled) |

---

## 📊 What's Included

| Category | Features |
|----------|---------|
| **Detection** | PPE (helmet/vest/gloves/goggles), fire/smoke, pose hazards, proximity to machinery |
| **AI/ML** | LangGraph autonomous agent, RAG chatbot (OSHA docs), SHAP explanations, drift detection, canary deployment |
| **Alerts** | WhatsApp (Twilio), Email (SMTP), Slack/Teams/JIRA webhooks, fire emergency overlay |
| **Data** | PostgreSQL, CSV/JSON export, weekly PDF reports, violation heatmap |
| **Enterprise** | RBAC, API key management, multi-site, shift management, audit log |
| **Portfolio** | Demo mode, onboarding wizard, dark mode, OpenAPI docs |

---

## 🐳 Docker Commands

```bash
docker compose up -d              # Start all services
docker compose down               # Stop all services
docker compose logs -f backend    # Watch backend logs
docker compose restart backend    # Restart after .env changes
docker compose ps                 # Check service health
```

---

## 🚀 Deploy to Production

**Railway (recommended for demos):**
```bash
railway login
railway link
railway up
# Set env vars in Railway dashboard
```

**DigitalOcean / any VPS:**
```bash
# On server:
git clone YOUR_REPO
cp .env.example .env && nano .env
docker compose -f docker-compose.yml up -d  # production only (no pgAdmin)
```

---

## 🐛 Troubleshooting

| Problem | Fix |
|---------|-----|
| No video feed | Set `DEMO_MODE=true` or check `VIDEO_SOURCE` in `.env` |
| Model not found | Run `python download_model.py` |
| DB connection failed | Check `DATABASE_URL` in `.env`, ensure PostgreSQL is running |
| Port 80 in use | Change `"80:80"` to `"8080:80"` in `docker-compose.yml` |
| Ollama not responding | Set `OPENAI_API_KEY` for GPT-4o fallback, or run Ollama locally |

---

Built by **Chandrukumar S** — AI/ML Engineer  
📧 kumarchandru646@gmail.com
