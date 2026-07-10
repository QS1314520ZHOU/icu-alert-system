@echo off
chcp 65001 >nul
title ICU智能预警系统
fltmc >nul 2>&1 || (
    echo 正在请求管理员权限...
    powershell -Command "Start-Process cmd -ArgumentList '/c %~s0' -Verb RunAs"
    exit
)

echo ================================
echo   ICU智能预警系统 清理端口并启动
echo ================================
echo.

echo [0/2] 清理占用端口：8000 和 5173
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000"') do (
    taskkill /F /PID %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173"') do (
    taskkill /F /PID %%a >nul 2>&1
)
echo 端口清理完毕
echo.

:: 启动后端
echo [1/2] 启动后端服务...
cd /d D:\icu-alert-system\backend
start "ICU-Backend" cmd /k "python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"

timeout /t 8 /nobreak >nul

:: 启动前端：改为 IPv4 0.0.0.0，不再绑定IPv6，解决权限报错
echo [2/2] 启动前端服务...
cd /d D:\icu-alert-system\frontend
start "ICU-Frontend" cmd /k "npm run dev -- --host 0.0.0.0 --port 5173"

echo.
echo ================================
echo   启动完成
echo   前端 http://localhost:5173
echo   外网 https://alert.jylb.fun
echo   后端 http://localhost:8000
echo ================================
echo.
pause