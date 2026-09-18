@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo   Brainwave Academy - Starting up
echo ============================================

where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo Python was not found on this computer.
    echo Please install Python 3.11 or later from https://www.python.org/downloads/
    echo IMPORTANT: On the first install screen, tick "Add python.exe to PATH".
    echo Then run this file again.
    echo.
    pause
    exit /b 1
)

if not exist ".venv" (
    echo.
    echo First-time setup - this only happens once and may take a few minutes...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install --upgrade pip
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)

if not exist ".env" (
    copy .env.example .env >nul
    echo.
    echo Created a .env settings file with default values.
    echo Edit it in Notepad to set a real SECRET_KEY and admin password before real use.
    echo.
)

echo.
echo Starting the server... your browser will open automatically.
echo Keep this window open while you use the app. Close it to stop the server.
echo.

start "" http://localhost:5000
python run.py

pause
