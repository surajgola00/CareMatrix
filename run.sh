#!/bin/bash
set -e

echo "Setting up CareMatrix..."

# ── SERVER ──────────────────────────────
echo ""
echo "[1/4] Creating Python virtual environment..."
cd Server
python3 -m venv .venv
source .venv/bin/activate

echo "[2/4] Installing Python dependencies..."
pip install -r requirements.txt

echo "[3/4] Starting FastAPI server on port 8000..."
uvicorn main:app --reload --port 8000 --host 0.0.0.0 &
SERVER_PID=$!
cd ..

# ── CLIENT ──────────────────────────────
echo ""
echo "[4/4] Installing and building React client..."
cd Client
bun install
bun run dev --host
echo "Serving built client on port 5173..."
CLIENT_PID=$!
cd ..

echo ""
echo "CareMatrix is running:"
echo "  Frontend  →  http://localhost:5173"
echo "  Backend   →  http://localhost:8000"
echo "  API Docs  →  http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop both servers."

trap "kill $SERVER_PID $CLIENT_PID 2>/dev/null; echo 'Stopped.'" INT
wait
