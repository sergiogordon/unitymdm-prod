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

DEVICE_ALIAS="${1:-Device}"
UNITY_PACKAGE="${2:-com.unity.app}"

if [ -z "$1" ]; then
    echo "Usage: ./enroll_device.sh <device_alias> [unity_package]"
    echo "Example: ./enroll_device.sh RackA-07 com.unity.app"
    echo ""
    echo "Required environment variables:"
    echo "  SERVER_URL - Your Replit deployment URL"
    echo "  ADMIN_KEY  - Admin key from Replit Secrets"
    exit 1
fi

echo "Enrolling device: $DEVICE_ALIAS"
echo "Unity package: $UNITY_PACKAGE"
echo "Server: $SERVER_URL"
echo ""

echo "1. Registering device with server..."
RESPONSE=$(curl -s -X POST "$SERVER_URL/v1/register?alias=$DEVICE_ALIAS" \
    -H "X-Admin: $ADMIN_KEY")

DEVICE_TOKEN=$(echo $RESPONSE | grep -o '"device_token":"[^"]*' | cut -d'"' -f4)
DEVICE_ID=$(echo $RESPONSE | grep -o '"device_id":"[^"]*' | cut -d'"' -f4)

if [ -z "$DEVICE_TOKEN" ]; then
    echo "Error: Failed to register device"
    echo "Response: $RESPONSE"
    exit 1
fi

echo "✓ Device registered successfully"
echo "  Device ID: $DEVICE_ID"
echo "  Token: ${DEVICE_TOKEN:0:20}..."
echo ""

echo "2. Checking ADB connection..."
adb devices | grep -q "device$"
if [ $? -ne 0 ]; then
    echo "Error: No ADB device connected"
    echo "Connect your device and enable USB debugging"
    exit 1
fi

echo "✓ ADB device connected"
echo ""

echo "3. Sending configuration to device..."
adb shell am broadcast \
    -a com.nexmdm.CONFIGURE \
    --es server_url "$SERVER_URL" \
    --es token "$DEVICE_TOKEN" \
    --es alias "$DEVICE_ALIAS" \
    --es unity_package "$UNITY_PACKAGE"

if [ $? -eq 0 ]; then
    echo "✓ Configuration sent successfully"
    echo ""
    echo "4. Verifying installation..."
    
    PACKAGE=$(adb shell pm list packages | grep com.nexmdm)
    if [ -z "$PACKAGE" ]; then
        echo "⚠  Warning: MDM app not installed on device"
        echo "   Install the APK first: adb install nexmdm.apk"
    else
        echo "✓ MDM app is installed"
    fi
    
    echo ""
    echo "========================================="
    echo "Device enrollment complete!"
    echo "========================================="
    echo "Device: $DEVICE_ALIAS"
    echo "ID: $DEVICE_ID"
    echo "Server: $SERVER_URL"
    echo ""
    echo "Next steps:"
    echo "1. Grant Usage Access permission (Settings > Apps > Special access > Usage access)"
    echo "2. Grant Notification Listener permission (Settings > Apps > Special access > Notification access)"
    echo "3. Device will start sending heartbeats every 2 minutes"
    echo ""
else
    echo "Error: Failed to send configuration"
    exit 1
fi
