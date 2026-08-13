@echo off
chcp 65001 >nul
title FB Shorts Ads Generator v3.0
cd /d "%~dp0"

echo.
echo ============================================================
echo   CHUYEN DONG FB SHORTS ADS GENERATOR v3.0
echo ============================================================
echo.
echo [!] Dang mo giao dien Web UI...
echo [!] Trinh duyet web se TU DONG MO trong 2-3 giay...
echo.

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" app2.py
) else if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" app2.py
) else (
    python app2.py
)

pause
