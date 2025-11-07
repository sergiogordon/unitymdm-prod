#!/bin/bash
# Frontend build wrapper for Replit VM deployment
# Ensures Next.js standalone build completes successfully

set -e

echo "🔨 Building Next.js frontend..."

# Install dependencies
echo "📦 Installing dependencies..."
npm ci --prefix frontend

# Build Next.js with standalone output
echo "⚙️ Running Next.js build..."
npm run build --prefix frontend

# Verify standalone build was created
if [ ! -d "frontend/.next/standalone" ]; then
  echo "❌ ERROR: Standalone build not found at frontend/.next/standalone"
  echo "Check that next.config.mjs has output: 'standalone' configured"
  exit 1
fi

echo "✅ Frontend build completed successfully"
echo "📁 Standalone bundle: frontend/.next/standalone"
