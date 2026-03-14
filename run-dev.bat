@echo off
setlocal enableextensions

cd /d "%~dp0"

rem Backend (FastAPI)
start "icu-backend" cmd /k "call run-backend.bat"

rem Wait for backend health endpoint
echo Waiting for backend health check (http://127.0.0.1:8000/health)...
powershell -NoProfile -Command "$ok=$false; for($i=0;$i -lt 45;$i++){ try { $r=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 2; if($r.StatusCode -eq 200){$ok=$true; break} } catch {}; Start-Sleep -Milliseconds 1000 }; if(-not $ok){ exit 1 }"
if errorlevel 1 (
    echo [ERROR] Backend failed to become healthy within 45 seconds.
    echo [ERROR] Please check backend window logs.
    endlocal
    exit /b 1
)
echo Backend is healthy.

rem Frontend (Vite)
start "icu-frontend" cmd /k "cd /d frontend && npm install && npm run dev -- --host 0.0.0.0 --port 5173"

echo Frontend starting at http://localhost:5173
endlocal