#!/bin/bash
# Production startup script for MDM system
# Runs both FastAPI backend and Next.js frontend

set -e

trap 'echo "🛑 Shutting down services..."; kill 0; exit' EXIT SIGTERM SIGINT

echo "🚀 Starting NexMDM Production Server..."

# Verify Next.js standalone build exists
echo "📦 Verifying Next.js standalone build..."
if [ ! -d "frontend/.next/standalone" ]; then
  echo "❌ ERROR: Next.js standalone build not found at frontend/.next/standalone"
  echo "Build must complete successfully before deployment starts."
  echo "Expected directory: frontend/.next/standalone"
  exit 1
fi

# Copy static files to standalone directory
if [ -d "frontend/.next/static" ]; then
  echo "Copying static assets..."
  mkdir -p frontend/.next/standalone/frontend/.next
  cp -r frontend/.next/static frontend/.next/standalone/frontend/.next/static
else
  echo "⚠️  Warning: No static assets found"
fi

# Copy public files if they exist
if [ -d "frontend/public" ]; then
  echo "Copying public assets..."
  mkdir -p frontend/.next/standalone/frontend
  cp -r frontend/public frontend/.next/standalone/frontend/public
fi

echo "✅ Static assets prepared"

# Start FastAPI backend on port 8000 in the background
echo "📡 Starting FastAPI backend on port 8000..."
cd server
python -m uvicorn main:app --host 0.0.0.0 --port 8000 &
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

# Wait for frontend to be ready
echo "⏳ Waiting for frontend to start..."
for i in {1..30}; do
  # Check both health endpoint and root route
  HEALTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5000/api/health 2>/dev/null || echo "000")
  ROOT_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5000/ 2>/dev/null || echo "000")
  
  if [ "$HEALTH_STATUS" = "200" ] && [ "$ROOT_STATUS" != "000" ]; then
    echo "✅ Frontend is ready! (Health: $HEALTH_STATUS, Root: $ROOT_STATUS)"
    break
  fi
  
  if [ $i -eq 30 ]; then
    echo "❌ Frontend failed health check (Health: $HEALTH_STATUS, Root: $ROOT_STATUS)"
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
    exit 1
  fi
  
  if [ $((i % 5)) -eq 0 ]; then
    echo "   Attempt $i/30: Health=$HEALTH_STATUS, Root=$ROOT_STATUS"
  fi
  sleep 1
done

echo "✨ NexMDM is now running!"
echo "   Frontend: http://0.0.0.0:5000"
echo "   Backend: http://0.0.0.0:8000"
echo "   Backend PID: $BACKEND_PID"
echo "   Frontend PID: $FRONTEND_PID"
echo ""
echo "Monitoring processes (will exit if either service fails)..."

# Wait for first process to exit (fail fast)
wait -n
EXIT_CODE=$?
echo "❌ Service exited with code $EXIT_CODE. Shutting down..."
exit $EXIT_CODE
