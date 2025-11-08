#!/bin/bash
# Production startup script for MDM system
# Runs both FastAPI backend and Next.js frontend

set -e

echo "🚀 Starting NexMDM Production Server..."

# Prepare Next.js standalone build (copy static assets)
echo "📦 Preparing Next.js standalone build..."
if [ -d "frontend/.next/standalone" ]; then
  # Copy static files to standalone directory
  if [ -d "frontend/.next/static" ]; then
    cp -r frontend/.next/static frontend/.next/standalone/frontend/.next/static
  fi
  # Copy public files if they exist
  if [ -d "frontend/public" ]; then
    cp -r frontend/public frontend/.next/standalone/frontend/public
  fi
  echo "✅ Static assets prepared"
else
  echo "⚠️  Warning: Next.js standalone build not found. Building now..."
  cd frontend && npm run build && cd ..
fi

# Start FastAPI backend on port 8000 in the background
echo "📡 Starting FastAPI backend on port 8000..."
cd server
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --limit-max-requests 1000000 &
BACKEND_PID=$!
cd ..

# Wait for backend to be ready
echo "⏳ Waiting for backend to start..."
for i in {1..30}; do
  if curl -s http://localhost:8000/healthz > /dev/null 2>&1; then
    echo "✅ Backend is ready!"
    break
  fi
  if [ $i -eq 30 ]; then
    echo "❌ Backend failed to start in time"
    kill $BACKEND_PID 2>/dev/null || true
    exit 1
  fi
  sleep 1
done

# Start Next.js frontend on port 5000
echo "🌐 Starting Next.js frontend on port 5000..."
cd frontend/.next/standalone/frontend
export BACKEND_URL=http://localhost:8000
export PORT=5000
export HOSTNAME=0.0.0.0
node server.js &
FRONTEND_PID=$!
cd ../../../..

echo "✨ NexMDM is now running!"
echo "   Frontend: http://0.0.0.0:5000"
echo "   Backend: http://0.0.0.0:8000"

# Wait for both processes
wait $BACKEND_PID $FRONTEND_PID
