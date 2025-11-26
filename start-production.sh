#!/bin/bash
set -e

echo "🚀 Starting NexMDM Production Server..."

# Start backend on port 8000
cd server
echo "Starting backend server..."
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2 &
BACKEND_PID=$!
echo "✅ Backend started on port 8000 (PID: $BACKEND_PID)"

# Wait for backend to be ready (check health endpoint)
echo "Waiting for backend to be ready..."
MAX_RETRIES=30
RETRY_COUNT=0
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -s http://localhost:8000/healthz > /dev/null 2>&1; then
        echo "✅ Backend is healthy"
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "Waiting for backend... ($RETRY_COUNT/$MAX_RETRIES)"
    sleep 1
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo "❌ Backend failed to start"
    exit 1
fi

# Start frontend on port 5000 using production build
cd ../frontend
echo "Starting frontend server..."
BACKEND_URL=http://localhost:8000 npm start -- -p 5000 -H 0.0.0.0 &
FRONTEND_PID=$!
echo "✅ Frontend started on port 5000 (PID: $FRONTEND_PID)"

echo "🎉 NexMDM is running!"
echo "   Backend:  http://localhost:8000"
echo "   Frontend: http://localhost:5000"

# Keep script running and wait for both processes
wait $BACKEND_PID $FRONTEND_PID
