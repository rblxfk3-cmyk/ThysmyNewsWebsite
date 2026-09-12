@echo off
setlocal EnableExtensions
title THYSMY Quick Start V2.5
cd /d "%~dp0"

set "PY_CMD="
python -c "import sys" >nul 2>nul
if not errorlevel 1 set "PY_CMD=python"

if not defined PY_CMD (
    python3 -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PY_CMD=python3"
)

if not defined PY_CMD (
    echo Python tak boleh run.
    pause
    exit /b 1
)

%PY_CMD% -c "import fastapi,uvicorn,requests" >nul 2>nul
if errorlevel 1 (
    echo Package belum lengkap. Guna start_windows.bat dulu.
    pause
    exit /b 1
)

start "" cmd /c "timeout /t 2 /nobreak >nul & start http://127.0.0.1:8000"
%PY_CMD% -m uvicorn app:app --host 0.0.0.0 --port 8000

pause
