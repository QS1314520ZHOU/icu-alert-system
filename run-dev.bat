@echo off
setlocal enableextensions

rem Always run from repo root
cd /d "%~dp0"

rem Backend (FastAPI)
rem If a local venv exists, activate it
set "BACKEND_CMD=cd /d backend && if exist .venv\Scripts\activate.bat (call .venv\Scripts\activate.bat) && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
start "icu-backend" cmd /k "%BACKEND_CMD%"

rem Frontend (Vite)
set "FRONTEND_CMD=cd /d frontend && npm install && npm run dev -- --host 0.0.0.0 --port 5173"
start "icu-frontend" cmd /k "%FRONTEND_CMD%"

endlocal