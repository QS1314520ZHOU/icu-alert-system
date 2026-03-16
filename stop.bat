@echo off
chcp 65001 >nul
echo 正在停止 ICU 预警系统...
taskkill /f /fi "WINDOWTITLE eq ICU-Backend*" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq ICU-Frontend*" >nul 2>&1
taskkill /f /im node.exe >nul 2>&1
echo 已停止
pause
