@echo off
title Arcade Online Launcher
cls

echo ====================================================
echo        ARCADE ONLINE MULTIPLAYER LAUNCHER
echo ====================================================
echo.

:: 1. Periksa apakah Python terpasang di sistem
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python tidak terdeteksi di PATH sistem!
    echo Silakan unduh dan pasang Python 3 dari https://www.python.org/
    echo Pastikan mencentang "Add Python to PATH" saat instalasi.
    echo.
    pause
    exit /b 1
)

:: 2. Periksa apakah windows-curses sudah terpasang
python -c "import curses" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [INFO] Menyiapkan antarmuka grafis arcade (windows-curses)...
    pip install windows-curses >nul 2>&1
)

:: 3. Jalankan Arcade Launcher
echo Memulai Arcade Launcher...
echo.
python -m launcher.main %*

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Launcher selesai dengan kode keluar %ERRORLEVEL%.
    pause
)

