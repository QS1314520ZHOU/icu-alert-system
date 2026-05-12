@echo off
chcp 65001 >nul
title ICU智能预警系统

echo ================================
echo   ICU智能预警系统 启动中...
echo ================================
echo.

:: 启动后端（只在本机 IPv4 暴露，给 Vite proxy 用）
echo [1/2] 启动后端服务...
cd /d D:\icu-alert-system\backend
start "ICU-Backend" cmd /k "python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"

:: 等待后端启动
timeout /t 8 /nobreak >nul

:: 启动前端（双栈监听，对外提供服务）
echo [2/2] 启动前端服务...
cd /d D:\icu-alert-system\frontend
start "ICU-Frontend" cmd /k "npm run dev -- --host :: --port 5173"

echo.
echo ================================
echo   启动完成
echo   前端 http://localhost:5173
echo   外网 https://alert.jylb.fun
echo   后端 http://localhost:8000
echo ================================
echo.
pause
