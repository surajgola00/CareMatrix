@echo off
echo Setting up CareMatrix...

:: ── SERVER ──────────────────────────────
echo.
echo [1/4] Creating Python virtual environment...
cd backend
if not exist .venv\Scripts\python.exe python -m venv .venv
call .venv\Scripts\activate.bat

echo [2/4] Installing Python dependencies...
pip install -r requirements.txt

echo [3/4] Starting FastAPI server on port 8000...
start "CareMatrix Server" cmd /k "call .venv\Scripts\activate.bat && uvicorn main:app --reload --port 8000"
cd ..

:: ── CLIENT ──────────────────────────────
echo.
echo [4/4] Installing and building React client...
cd frontend
if not exist node_modules npm install
call npm run build

echo Starting frontend on port 5173...
start "CareMatrix Client" cmd /k "npm run preview -- --host 127.0.0.1 --port 5173"
cd ..

echo.
echo CareMatrix is running:
echo   Frontend  ^>  http://localhost:5173
echo   Backend   ^>  http://localhost:8000
echo   API Docs  ^>  http://localhost:8000/docs
echo.
echo Both servers are running in separate windows.
echo Close those windows to stop the servers.
pause
