@echo off
chcp 65001 >nul
title Cai dat FB Shorts Ads Generator
cd /d "%~dp0"

echo.
echo ============================================================
echo   CAI DAT FB SHORTS ADS GENERATOR
echo   Chi can chay file nay 1 LAN DUY NHAT
echo ============================================================
echo.

echo [1/3] Kiem tra Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo LOI: Chua cai Python hoac chua add Python vao PATH!
    pause
    exit /b 1
)
echo OK - Python da san sang

echo [2/3] Tao môi truong Python (.venv)...
if exist ".venv" (
    echo Da co môi truong .venv - bo qua buoc nay
) else (
    python -m venv .venv
    echo OK - Tao moi truong .venv thanh cong
)

echo [3/3] Cai dat thu vien...
".venv\Scripts\pip.exe" install -r requirements.txt edge-tts mutagen nest-asyncio gradio

echo.
echo ============================================================
echo   CAI DAT HOAN TAT!
echo   Hay chay lai file KHOI_DONG.bat de mo web!
echo ============================================================
echo.
pause
