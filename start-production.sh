#!/bin/bash
set -e

echo "🚀 Starting NexMDM Production Server..."

# Start backend on port 8000
cd server
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2 &
BACKEND_PID=$!
echo "✅ Backend started on port 8000 (PID: $BACKEND_PID)"

# Wait for backend to be ready
sleep 3

# Start frontend on port 5000 (required for deployment)
cd ../frontend
BACKEND_URL=http://localhost:8000 npm run dev -- -p 5000 -H 0.0.0.0 &
FRONTEND_PID=$!
echo "✅ Frontend started on port 5000 (PID: $FRONTEND_PID)"

echo "🎉 NexMDM is running!"
echo "   Backend:  http://localhost:8000"
echo "   Frontend: http://localhost:5000"

# Keep script running and wait for both processes
wait $BACKEND_PID $FRONTEND_PID