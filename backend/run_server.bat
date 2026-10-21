@echo off
REM CareMatrix Backend Startup Script (Windows)
REM Run this to start the FastAPI server

echo.
echo ================================================
echo   CareMatrix Backend Server Startup
echo ================================================
echo.

REM Check if virtual environment exists
if not exist venv (
    echo [*] Creating virtual environment...
    python -m venv venv
    echo [+] Virtual environment created
)

REM Activate virtual environment
echo [*] Activating virtual environment...
call venv\Scripts\activate.bat

REM Install dependencies
echo [*] Installing dependencies...
pip install -r requirements.txt -q

REM Check if .env exists
if not exist .env (
    echo [!] .env file not found
    echo [*] Creating .env from .env.example...
    copy .env.example .env
    echo [!] Please update .env with your database credentials
    echo [!] DATABASE_URL=mysql+mysqlconnector://root:password@localhost:3306/carematrix
    echo.
    pause
)

REM Start server
echo.
echo [+] Starting CareMatrix Backend Server...
echo.
echo ================================================
echo     Server running at: http://localhost:8000
echo     API Docs: http://localhost:8000/docs
echo     Press Ctrl+C to stop
echo ================================================
echo.

uvicorn main:app --host 0.0.0.0 --port 8000 --reload

pause
