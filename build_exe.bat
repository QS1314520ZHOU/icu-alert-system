@echo off
chcp 65001 >nul
setlocal

cd /d %~dp0
powershell -ExecutionPolicy Bypass -File "%~dp0build_exe.ps1" %*

endlocal
