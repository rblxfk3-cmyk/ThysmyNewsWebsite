@echo off
setlocal EnableExtensions
title THYSMY Fundamental Engine V3.0
cd /d "%~dp0"

echo.
echo ============================================================
echo   THYSMY FUNDAMENTAL ENGINE V3.0
echo ============================================================
echo.

REM ------------------------------------------------------------
REM 1) FIND WORKING PYTHON
REM ------------------------------------------------------------
set "PY_CMD="

echo [1/3] Checking Python...

python -c "import sys" >nul 2>nul
if not errorlevel 1 set "PY_CMD=python"

if not defined PY_CMD (
    python3 -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PY_CMD=python3"
)

if not defined PY_CMD (
    py -3 -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PY_CMD=py -3"
)

if not defined PY_CMD (
    echo.
    echo [ERROR] Python tak dapat dijalankan.
    echo Test dalam PowerShell:
    echo     python --version
    echo.
    pause
    exit /b 1
)

echo Python command: %PY_CMD%
%PY_CMD% -c "import sys; print('Python',sys.version.split()[0]); print(sys.executable)"
if errorlevel 1 (
    echo [ERROR] Python command gagal.
    pause
    exit /b 1
)

REM ------------------------------------------------------------
REM 2) CHECK / INSTALL PACKAGES
REM ------------------------------------------------------------
echo.
echo [2/3] Checking packages...

%PY_CMD% -c "import fastapi, uvicorn, requests" >nul 2>nul
if errorlevel 1 (
    echo Missing package detected. Installing once...
    echo.
    %PY_CMD% -m pip install --disable-pip-version-check --no-warn-script-location -r requirements.txt

    if errorlevel 1 (
        echo.
        echo [ERROR] Package installation really failed.
        echo Screenshot the lines immediately above this message.
        echo.
        pause
        exit /b 1
    )

    echo.
    echo Package installation completed successfully.
) else (
    echo Packages ready - skip install.
)

REM Double-check imports after install
%PY_CMD% -c "import fastapi, uvicorn, requests" >nul 2>nul
if errorlevel 1 (
    echo.
    echo [ERROR] Packages installed but Python still cannot import them.
    echo.
    pause
    exit /b 1
)

REM ------------------------------------------------------------
REM 3) START SERVER
REM ------------------------------------------------------------
echo.
echo [3/3] Starting server...
echo.
echo ============================================================
echo   SERVER READY
echo   http://127.0.0.1:8000
echo ============================================================
echo.
echo Jangan tutup window ini semasa guna web.
echo Tekan CTRL+C untuk stop.
echo.

start "" cmd /c "timeout /t 2 /nobreak >nul & start http://127.0.0.1:8000"

%PY_CMD% -m uvicorn app:app --host 0.0.0.0 --port 8000

echo.
echo ============================================================
echo Server stopped.
echo Kalau ada error, screenshot bahagian tepat di atas ini.
echo ============================================================
pause
