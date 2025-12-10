#!/bin/bash
set -e

echo "🚀 Starting NexMDM Production Server..."
echo "Environment: REPLIT_DEPLOYMENT=$REPLIT_DEPLOYMENT"

# Check required environment variables
if [ -z "$DATABASE_URL" ]; then
    echo "⚠️ WARNING: DATABASE_URL not set"
fi

# Start backend on port 8000 with log output visible
cd server
echo "Starting backend server..."
echo "Working directory: $(pwd)"

# Start uvicorn and redirect stderr to stdout so we can see errors
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2 2>&1 &
BACKEND_PID=$!
echo "✅ Backend process started (PID: $BACKEND_PID)"

# Wait for backend to be ready (check health endpoint)
# Increased timeout to 60 seconds for cold start
echo "Waiting for backend to be ready..."
MAX_RETRIES=60
RETRY_COUNT=0
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    # Check if backend process is still running
    if ! kill -0 $BACKEND_PID 2>/dev/null; then
        echo "❌ Backend process died unexpectedly"
        exit 1
    fi
    
    if curl -s http://localhost:8000/healthz > /dev/null 2>&1; then
        echo "✅ Backend is healthy after $RETRY_COUNT seconds"
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "Waiting for backend... ($RETRY_COUNT/$MAX_RETRIES)"
    sleep 1
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo "❌ Backend failed to respond to health check within $MAX_RETRIES seconds"
    echo "Checking if process is still running..."
    if kill -0 $BACKEND_PID 2>/dev/null; then
        echo "Backend process is running but not responding"
        echo "Attempting to get more info..."
        curl -v http://localhost:8000/healthz 2>&1 || true
    else
        echo "Backend process has died"
    fi
    exit 1
fi

# Start frontend on port 5000 using production build
cd ../frontend
echo "Starting frontend server..."
echo "BACKEND_URL environment variable: ${BACKEND_URL:-'not set (will use default)'}"

# Check if standalone build exists (Next.js standalone mode)
# BACKEND_URL is automatically available from .replit [userenv.shared] section
if [ -f ".next/standalone/server.js" ]; then
    echo "Using standalone build..."
    PORT=5000 HOSTNAME=0.0.0.0 node .next/standalone/server.js &
else
    echo "Standalone build not found, using npm start..."
    npm start -- -p 5000 -H 0.0.0.0 &
fi

FRONTEND_PID=$!
echo "✅ Frontend started on port 5000 (PID: $FRONTEND_PID)"

echo "🎉 NexMDM is running!"
echo "   Backend:  http://localhost:8000"
echo "   Frontend: http://localhost:5000"

# Keep script running and wait for both processes
wait $BACKEND_PID $FRONTEND_PID
