# Contributing to Industrial Safety Monitor

Thank you for contributing! This guide covers everything you need to set up locally,
make a change, and open a pull request.

---

## 📋 Table of Contents

1. [Development Setup](#-development-setup)
2. [Project Structure](#-project-structure)
3. [Running Tests](#-running-tests)
4. [Making a Change](#-making-a-change)
5. [Commit Conventions](#-commit-conventions)
6. [Database Changes (Alembic)](#-database-changes-alembic)
7. [Adding an API Endpoint](#-adding-an-api-endpoint)
8. [Code Style](#-code-style)
9. [Opening a Pull Request](#-opening-a-pull-request)

---

## 🚀 Development Setup

### Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.11+ | [python.org](https://www.python.org/) |
| Node.js | 20+ | [nodejs.org](https://nodejs.org/) |
| Git | 2.40+ | [git-scm.com](https://git-scm.com/) |

### Clone & Install

```bash
git clone https://github.com/chandrukumar/industrial-safety-monitoring
cd industrial-safety-monitoring

# Backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / Mac

pip install -r requirements.txt -r requirements-dev.txt

# Apply DB migrations
alembic upgrade head

# Frontend
cd frontend
npm install
```

### Configure Environment

```bash
cp .env.example .env
# Edit .env — minimum:
# API_KEY=any-secret-key-for-dev
# DEMO_MODE=true
# DATABASE_URL=sqlite+aiosqlite:///./safety_monitor.db
```

### Start Dev Servers

```bash
# Backend (from project root)
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend (separate terminal)
cd frontend && npm run dev
```

Dashboard: http://localhost:5173  
API docs: http://localhost:8000/docs

---

## 🏗️ Project Structure

```
backend/
├── main.py           # App factory + middleware
├── models.py         # Pydantic v2 schemas + SQLModel tables
├── database.py       # Async engine + session factory
├── routes/           # One file per API domain (24 files → 39 endpoints)
├── agent/            # LangGraph 8-node workflow
├── inference/        # YOLOv8 + ByteTrack + MediaPipe pipeline
├── mlops/            # MLflow + canary router
├── identity/         # DeepFace + risk scorer
├── middleware/        # Rate limiter
└── ...

frontend/src/
├── components/       # 27 React components (12 dashboard tabs)
├── hooks/            # Custom React hooks
└── App.jsx           # Root component + routing

tests/                # pytest unit + integration tests
alembic/versions/     # DB migration scripts
.github/              # CI workflow + PR/issue templates
```

---

## 🧪 Running Tests

```bash
# All tests
pytest tests/ -v

# Specific module
pytest tests/test_auth.py -v

# With coverage report
pytest tests/ --cov=backend --cov-report=term-missing

# Fast check (fail on first error)
pytest tests/ -x -q
```

### Test full API (39 endpoints)
```bash
# Start backend first
python test_endpoints.py
```

---

## 🔄 Making a Change

1. **Create a feature branch** from `main`:
   ```bash
   git checkout -b feat/your-feature-name
   ```

2. **Make your changes** — see domain-specific guides below

3. **Run tests** locally before pushing:
   ```bash
   pytest tests/ -q
   ruff check .
   ```

4. **Commit** following the conventions below

5. **Push and open a PR** using the template

---

## 📝 Commit Conventions

We follow [Conventional Commits](https://www.conventionalcommits.org/).

```
<type>(<scope>): <short description>

[optional body]

[optional footer]
```

### Types

| Type | When to use |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `test` | Adding/fixing tests |
| `docs` | Documentation only |
| `refactor` | Code restructuring (no behavior change) |
| `perf` | Performance improvement |
| `chore` | Build, CI, dependency updates |
| `security` | Security fix |

### Examples

```bash
git commit -m "feat(workers): add 7-day rolling risk score endpoint"
git commit -m "fix(cameras): accept rtsp:// URL scheme in Pydantic v2"
git commit -m "test(auth): add 401/403 regression tests for all protected routes"
git commit -m "chore(deps): pin numpy to 1.26.4 for compatibility"
```

---

## 🗄️ Database Changes (Alembic)

**Never edit the DB directly.** All schema changes must go through Alembic migrations.

```bash
# 1. Update the SQLModel class in backend/models.py

# 2. Auto-generate migration
alembic revision --autogenerate -m "add index on worker_id"

# 3. Review the generated file in alembic/versions/
#    Make sure it looks correct before applying

# 4. Apply migration
alembic upgrade head

# 5. Include the migration file in your PR
```

**SQLite note:** Use `render_as_batch=True` in `env.py` (already set) — SQLite
doesn't support `ALTER COLUMN`, so Alembic uses batch mode (temp table rename).

---

## 🔌 Adding an API Endpoint

1. **Create or edit** a route file in `backend/routes/your_route.py`
2. **Register the router** in `backend/main.py` under `create_app()`
3. **Add the Pydantic schema** to `backend/models.py` (request + response)
4. **Write a test** in `tests/test_your_feature.py`
5. **Add to README.md** endpoint table
6. **Update CHANGELOG.md** under `[Unreleased]`

---

## 🎨 Code Style

### Python

We use **ruff** for both linting and formatting.

```bash
# Check
ruff check .

# Auto-fix
ruff check . --fix

# Format
ruff format .
```

Config: `pyproject.toml` → `[tool.ruff]`  
Rules: E, F, I (isort), N (naming), UP (pyupgrade), B (bugbear), SIM

### JavaScript/React

We use **ESLint** (config: `frontend/eslint.config.js`).

```bash
cd frontend
npm run lint
```

### Key Python conventions

- Type annotations on all public functions
- `loguru` for logging (not `print`)
- SQLModel for DB tables, Pydantic v2 for request/response schemas
- `CURRENT_TIMESTAMP` (not `NOW()`) for SQLite compatibility
- `.model_dump()` (not `**model_instance`) for Pydantic v2

---

## 📬 Opening a Pull Request

1. Make sure all tests pass: `pytest tests/ -q`
2. Push your branch: `git push origin feat/your-feature-name`
3. Open PR on GitHub → use the **PR template**
4. Fill in all checklist items
5. Request review from `@chandrukumar`

PRs that fail CI (ruff, mypy, pytest) will not be merged.

---

## 🙋 Questions?

Open a [Discussion](https://github.com/chandrukumar/industrial-safety-monitoring/discussions)
or email: kumarchandru646@gmail.com
