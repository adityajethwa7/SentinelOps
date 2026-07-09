#!/usr/bin/env bash
set -e

echo "======================================"
echo "    Starting SentinelOps System       "
echo "======================================"

# Ensure virtual environment exists
if [ ! -d ".venv" ]; then
    echo "Virtual environment not found! Please run setup first."
    exit 1
fi

source .venv/bin/activate

# Start FastAPI backend in the background
echo "-> Starting FastAPI backend on http://localhost:8000..."
export PYTHONPATH=src
uvicorn sentinelops.api.server:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Start Vite frontend
echo "-> Starting Vite frontend on http://localhost:5173..."
cd frontend
# Ensure node_modules exist
if [ ! -d "node_modules" ]; then
    npm install
fi
npm run dev &
FRONTEND_PID=$!

echo "======================================"
echo " SentinelOps is running! Press Ctrl+C to stop."
echo "======================================"

# Trap termination signals to kill background processes gracefully
trap "echo 'Shutting down...'; kill $BACKEND_PID $FRONTEND_PID; exit 0" SIGINT SIGTERM EXIT

# Wait indefinitely until interrupted
wait
