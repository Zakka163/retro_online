@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel% equ 0 (
    python setup_log_ssh.py
    goto :done
)

where py >nul 2>nul
if %errorlevel% equ 0 (
    py setup_log_ssh.py
    goto :done
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_log_ssh.ps1"

:done
echo.
pause
