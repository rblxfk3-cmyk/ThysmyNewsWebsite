@echo off
setlocal EnableExtensions
title THYSMY Fundamental Engine V2.4
cd /d "%~dp0"

echo.
echo ============================================================
echo   THYSMY FUNDAMENTAL ENGINE V2.4
echo ============================================================
echo.

REM ============================================================
REM 1) FIND A PYTHON THAT ACTUALLY RUNS
REM    Prefer "python" because this PC already used it before.
REM ============================================================
set "PY_CMD="

echo [1/3] Checking Python...

where python >nul 2>nul
if %errorlevel%==0 (
    python -c "import sys; print(sys.executable)" >nul 2>nul
    if %errorlevel%==0 set "PY_CMD=python"
)

if not defined PY_CMD (
    where python3 >nul 2>nul
    if %errorlevel%==0 (
        python3 -c "import sys; print(sys.executable)" >nul 2>nul
        if %errorlevel%==0 set "PY_CMD=python3"
    )
)

if not defined PY_CMD (
    where py >nul 2>nul
    if %errorlevel%==0 (
        py -3 -c "import sys; print(sys.executable)" >nul 2>nul
        if %errorlevel%==0 set "PY_CMD=py -3"
    )
)

if not defined PY_CMD (
    echo.
    echo [ERROR] Tak jumpa Python yang boleh execute.
    echo.
    echo Cuba buka CMD biasa dan taip:
    echo     python --version
    echo.
    echo Kalau command tu gagal, Python installation Windows perlu repair.
    echo.
    pause
    exit /b 1
)

echo Python command: %PY_CMD%
%PY_CMD% -c "import sys; print('Python',sys.version.split()[0]); print(sys.executable)"
if not %errorlevel%==0 (
    echo [ERROR] Python command gagal.
    pause
    exit /b 1
)

REM ============================================================
REM 2) DEPENDENCIES - SKIP INSTALL IF ALREADY PRESENT
REM ============================================================
echo.
echo [2/3] Checking packages...
%PY_CMD% -c "import fastapi, uvicorn, requests; print('Packages OK')" >nul 2>nul

if %errorlevel%==0 (
    echo Packages ready - no installation needed.
) else (
    echo Missing package detected. Installing once...
    %PY_CMD% -m pip install --disable-pip-version-check --no-warn-script-location -r requirements.txt

    if not %errorlevel%==0 (
        echo.
        echo [ERROR] Package installation failed.
        echo.
        pause
        exit /b 1
    )
)

REM ============================================================
REM 3) START SERVER USING SAME WORKING PYTHON
REM ============================================================
echo.
echo [3/3] Starting server...
echo.
echo ============================================================
echo   SERVER READY
echo   http://127.0.0.1:8000
echo ============================================================
echo.
echo Jangan tutup window ini.
echo Tekan CTRL+C untuk stop server.
echo.

start "" cmd /c "timeout /t 2 /nobreak >nul & start http://127.0.0.1:8000"

%PY_CMD% -m uvicorn app:app --host 0.0.0.0 --port 8000

echo.
echo ============================================================
echo Server stopped / failed.
echo Screenshot error di atas kalau masih ada masalah.
echo ============================================================
pause
