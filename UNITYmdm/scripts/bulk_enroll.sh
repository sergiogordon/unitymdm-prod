#!/bin/bash

if [ -z "$SERVER_URL" ]; then
    echo "Error: SERVER_URL environment variable not set"
    echo ""
    echo "Set SERVER_URL to your Replit deployment URL:"
    echo "  export SERVER_URL=\"https://your-replit-app.repl.dev\""
    echo ""
    exit 1
fi

if [ -z "$ADMIN_KEY" ]; then
    echo "Error: ADMIN_KEY environment variable not set"
    echo ""
    echo "Set ADMIN_KEY from your Replit Secrets:"
    echo "  export ADMIN_KEY=\"your-admin-key-here\""
    echo ""
    exit 1
fi

if [ ! -f "devices.csv" ]; then
    echo "Error: devices.csv not found"
    echo ""
    echo "Create a devices.csv file with format:"
    echo "alias,unity_package"
    echo "RackA-01,com.unity.app"
    echo "RackA-02,com.unity.app"
    exit 1
fi

echo "Bulk enrollment starting..."
echo "Server: $SERVER_URL"
echo ""

tail -n +2 devices.csv | while IFS=',' read -r alias package; do
    if [ -n "$alias" ]; then
        echo "========================================"
        echo "Enrolling: $alias"
        echo "========================================"
        ./enroll_device.sh "$alias" "${package:-com.unity.app}"
        echo ""
        echo "Press Enter to continue to next device (or Ctrl+C to stop)..."
        read
    fi
done

echo "Bulk enrollment complete!"
