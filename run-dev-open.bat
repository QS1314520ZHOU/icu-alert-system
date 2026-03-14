@echo off
setlocal enableextensions

rem Always run from repo root
cd /d "%~dp0"

rem Backend (FastAPI)
set "BACKEND_CMD=cd /d backend && if exist .venv\Scripts\activate.bat (call .venv\Scripts\activate.bat) && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
start "icu-backend" cmd /k "%BACKEND_CMD%"

rem Wait for backend health endpoint before starting frontend
echo Waiting for backend health check (http://127.0.0.1:8000/health)...
powershell -NoProfile -Command "$ok=$false; for($i=0;$i -lt 45;$i++){ try { $r=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 2; if($r.StatusCode -eq 200){$ok=$true; break} } catch {}; Start-Sleep -Milliseconds 1000 }; if(-not $ok){ exit 1 }"
if errorlevel 1 (
  echo [ERROR] Backend failed to become healthy within 45 seconds.
  echo [ERROR] Please check backend window logs (Mongo/Redis/env config).
  endlocal
  exit /b 1
)

rem Frontend (Vite) - fast mode (no npm install)
set "FRONTEND_CMD=cd /d frontend && npm run dev -- --host 0.0.0.0 --port 5173"
start "icu-frontend" cmd /k "%FRONTEND_CMD%"

rem Open browser after a short delay
timeout /t 3 /nobreak >nul
start "" "http://localhost:5173"

endlocal
