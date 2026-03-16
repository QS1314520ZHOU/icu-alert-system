@echo off
chcp 65001 >nul
title ICU智能预警系统

echo ================================
echo   ICU智能预警系统 启动中...
echo ================================
echo.

:: 启动后端
echo [1/2] 启动后端服务...
cd /d D:\icu-alert-system\backend
start "ICU-Backend" cmd /k "python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"

:: 等待后端启动
timeout /t 5 /nobreak >nul

:: 启动前端
echo [2/2] 启动前端服务...
cd /d D:\icu-alert-system\frontend
start "ICU-Frontend" cmd /k "npm run dev -- --host 0.0.0.0 --port 5173"

echo.
echo ================================
echo   启动完成！
echo   前端: http://localhost:5173
echo   后端: http://localhost:8000
echo ================================
echo.
echo 关闭此窗口不影响服务运行
echo 要停止服务请关闭 ICU-Backend 和 ICU-Frontend 两个窗口
pause
