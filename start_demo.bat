@echo off
echo ============================================================
echo   Industrial Safety Monitor — Demo Startup
echo ============================================================
echo.

cd /d "%~dp0"

REM ── Step 1: Seed demo data ──────────────────────────────────
echo [1/3] Seeding demo data...
.venv\Scripts\python.exe scripts\demo_seed.py 2>nul
if errorlevel 1 (
    echo      First time seed...
    .venv\Scripts\python.exe scripts\demo_seed.py --reset 2>nul
)
echo      Done.
echo.

REM ── Step 2: Start backend ────────────────────────────────────
echo [2/3] Starting backend API on http://localhost:8000 ...
start "Safety Monitor Backend" /B .venv\Scripts\uvicorn.exe backend.main:app --host 127.0.0.1 --port 8000 --log-level warning
timeout /t 5 /nobreak >nul
echo      Backend started.
echo.

REM ── Step 3: Start frontend ───────────────────────────────────
echo [3/3] Starting frontend on http://localhost:5173 ...
cd frontend
start "Safety Monitor Frontend" /B node_modules\.bin\vite.cmd --port 5173
cd ..
timeout /t 4 /nobreak >nul
echo      Frontend started.
echo.

echo ============================================================
echo   DEMO READY
echo ============================================================
echo.
echo   Frontend:  http://localhost:5173
echo   Backend:   http://localhost:8000
echo   API Docs:  http://localhost:8000/docs
echo.
echo   API Key:   (from .env API_KEY)
echo.
echo   Panels available:
echo     Dashboard, Violations, Heatmap, Workers, Cameras,
echo     Alerts, Chat, Reports, MLOps, Fire, Proximity,
echo     Pose Hazards, Escalation, Attendance, Permits,
echo     Industry PPE, Organizations, Billing
echo.
echo   Press Ctrl+C in each terminal to stop.
echo ============================================================
pause
