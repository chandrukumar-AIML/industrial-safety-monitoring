@echo off
title Industrial Safety Monitor - Dev Server
echo.
echo ============================================
echo   Industrial Safety Monitor - Starting Up
echo ============================================
echo.
echo Your WiFi IP: 10.75.225.143
echo.
echo   Frontend : http://localhost:5173
echo   Frontend : http://10.75.225.143:5173  (WiFi)
echo   Backend  : http://localhost:8000
echo   Backend  : http://10.75.225.143:8000  (WiFi)
echo   API Docs : http://localhost:8000/docs
echo.
echo Starting Backend...
start "Safety Backend" cmd /k "cd /d C:\Users\kumar\industrial-safety-monitoring && .venv\Scripts\activate && set DEMO_MODE=true && .venv\Scripts\uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload"

timeout /t 3 /nobreak >nul

echo Starting Frontend...
start "Safety Frontend" cmd /k "cd /d C:\Users\kumar\industrial-safety-monitoring\frontend && npm run dev"

echo.
echo Both servers starting in separate windows...
echo Open http://localhost:5173 in your browser.
echo.
pause
