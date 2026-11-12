@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo     SETUP SSH KEY WINDOWS KE SERVER VPS ARCADE     
echo ===================================================

set VPS_HOST=217.216.146.15
set VPS_PORT=20157
set VPS_USER=root
set REMOTE_DIR=/root/log_testing

where ssh >nul 2>nul
if %errorlevel% neq 0 (
    echo [X] OpenSSH Client tidak ditemukan di Windows Anda!
    echo     Aktifkan via: Settings -^> Apps -^> Optional Features -^> OpenSSH Client.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_log_ssh.ps1"

echo.
pause

