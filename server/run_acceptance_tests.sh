#!/bin/bash

echo "=========================================="
echo "NexMDM Acceptance Test Suite"
echo "=========================================="
echo ""

cd "$(dirname "$0")"

if [ -z "$ADMIN_KEY" ]; then
    export ADMIN_KEY="admin"
    echo "⚠  ADMIN_KEY not set, using default: 'admin'"
fi

echo "Running acceptance tests..."
echo ""

pytest tests/ -v --tb=short

exit_code=$?

echo ""
if [ $exit_code -eq 0 ]; then
    echo "=========================================="
    echo "✅ All acceptance tests passed!"
    echo "=========================================="
else
    echo "=========================================="
    echo "❌ Some tests failed (exit code: $exit_code)"
    echo "=========================================="
fi

exit $exit_code
