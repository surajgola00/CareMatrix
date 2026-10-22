@echo off
setlocal EnableExtensions
cd /d "%~dp0"

for /f "tokens=2 delims=:" %%I in ('ipconfig ^| findstr /C:"IPv4 Address"') do for /f "tokens=*" %%J in ("%%I") do if not defined LAN_IP set "LAN_IP=%%J"
if not defined LAN_IP (
  echo Could not find a LAN IPv4 address. Connect to Wi-Fi or Ethernet first.
  pause
  exit /b 1
)

echo CareMatrix LAN demo
echo Laptop address: %LAN_IP%
echo Frontend:       http://%LAN_IP%:5173
echo Backend docs:   http://%LAN_IP%:8000/docs
echo.
echo Other devices must be connected to the same network.
echo.

echo Close any older CareMatrix server windows before starting a new demo session.

netstat -ano | findstr /C:"0.0.0.0:8000" | findstr /C:"LISTENING" >nul
if errorlevel 1 start "CareMatrix Backend" powershell -NoExit -ExecutionPolicy Bypass -Command "Set-Location '%~dp0backend'; & '.venv\Scripts\activate'; & python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000"
if not errorlevel 1 echo Backend already listening on port 8000; keeping it.
netstat -ano | findstr /C:"0.0.0.0:5173" | findstr /C:"LISTENING" >nul
if errorlevel 1 start "CareMatrix Frontend" powershell -NoExit -ExecutionPolicy Bypass -Command "$env:VITE_API_BASE='http://%LAN_IP%:8000'; Set-Location '%~dp0frontend'; npm run dev -- --host 0.0.0.0 --port 5173"
if not errorlevel 1 echo Frontend already listening on port 5173; keeping it.

echo If another device cannot connect, allow Python and Node.js through Windows Firewall
echo on Private networks, or run the firewall commands documented in README.md.
pause
