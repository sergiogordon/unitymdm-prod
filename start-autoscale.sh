#!/bin/bash
# Autoscale deployment startup script - Frontend only
# The backend should be deployed as a separate service

set -e

echo "🚀 Starting NexMDM Frontend (Autoscale Mode)..."

# Verify Next.js standalone build exists
if [ ! -d "frontend/.next/standalone" ]; then
  echo "❌ ERROR: Next.js standalone build not found"
  echo "Please ensure the build completed successfully"
  exit 1
fi

# Copy static files to standalone directory
if [ -d "frontend/.next/static" ]; then
  echo "📦 Copying static assets..."
  mkdir -p frontend/.next/standalone/frontend/.next
  cp -r frontend/.next/static frontend/.next/standalone/frontend/.next/static
fi

# Copy public files if they exist
if [ -d "frontend/public" ]; then
  echo "📦 Copying public assets..."
  mkdir -p frontend/.next/standalone/frontend
  cp -r frontend/public frontend/.next/standalone/frontend/public
fi

# Start Next.js frontend on port 5000
# Note: The frontend's API proxy will connect to the backend service
echo "🌐 Starting Next.js frontend on port 5000..."
cd frontend/.next/standalone/frontend
export PORT=5000
export HOSTNAME=0.0.0.0

# For Autoscale, the backend URL should point to the deployed backend service
# You'll need to set this as a deployment secret
export BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"

echo "✨ Frontend starting..."
echo "   Listening on: http://0.0.0.0:5000"
echo "   Backend URL: $BACKEND_URL"

# Start the standalone Next.js server
exec node server.js