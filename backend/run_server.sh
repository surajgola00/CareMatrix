#!/bin/bash
# CareMatrix Backend Startup Script (Linux/Mac)
# Run this to start the FastAPI server

echo ""
echo "================================================"
echo "  CareMatrix Backend Server Startup"
echo "================================================"
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "[*] Creating virtual environment..."
    python3 -m venv venv
    echo "[+] Virtual environment created"
fi

# Activate virtual environment
echo "[*] Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "[*] Installing dependencies..."
pip install -r requirements.txt -q

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "[!] .env file not found"
    echo "[*] Creating .env from .env.example..."
    cp .env.example .env
    echo "[!] Please update .env with your database credentials"
    echo "[!] DATABASE_URL=mysql+mysqlconnector://root:password@localhost:3306/carematrix"
    echo ""
    read -p "Press Enter to continue..."
fi

# Start server
echo ""
echo "[+] Starting CareMatrix Backend Server..."
echo ""
echo "================================================"
echo "    Server running at: http://localhost:8000"
echo "    API Docs: http://localhost:8000/docs"
echo "    Press Ctrl+C to stop"
echo "================================================"
echo ""

uvicorn main:app --host 0.0.0.0 --port 8000 --reload
