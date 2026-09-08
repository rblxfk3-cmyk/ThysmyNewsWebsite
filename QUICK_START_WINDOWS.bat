@echo off
setlocal
title THYSMY Quick Start V2.4
cd /d "%~dp0"

set "PY_CMD=python"
python -c "import sys" >nul 2>nul
if not %errorlevel%==0 set "PY_CMD=python3"

%PY_CMD% -c "import sys" >nul 2>nul
if not %errorlevel%==0 (
    echo Python gagal dijalankan.
    pause
    exit /b 1
)

start "" cmd /c "timeout /t 2 /nobreak >nul & start http://127.0.0.1:8000"
%PY_CMD% -m uvicorn app:app --host 0.0.0.0 --port 8000

pause
