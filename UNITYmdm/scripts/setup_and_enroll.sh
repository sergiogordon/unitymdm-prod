#!/bin/bash

# NexMDM Device Setup & Enrollment Script
# This script combines device optimization with MDM installation and enrollment

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Required environment variables
if [ -z "$SERVER_URL" ]; then
    echo -e "${RED}Error: SERVER_URL environment variable not set${NC}"
    echo ""
    echo "Set SERVER_URL to your Replit deployment URL:"
    echo "  export SERVER_URL=\"https://your-replit-app.repl.dev\""
    echo ""
    exit 1
fi

if [ -z "$ADMIN_KEY" ]; then
    echo -e "${RED}Error: ADMIN_KEY environment variable not set${NC}"
    echo ""
    echo "Set ADMIN_KEY from your Replit Secrets:"
    echo "  export ADMIN_KEY=\"your-admin-key-here\""
    echo ""
    exit 1
fi

DEVICE_ALIAS="${1:-Device}"
UNITY_PACKAGE="${2:-com.unity.app}"

if [ -z "$1" ]; then
    echo "Usage: ./setup_and_enroll.sh <device_alias> [unity_package]"
    echo "Example: ./setup_and_enroll.sh RackA-07 com.unity.app"
    echo ""
    echo "Required environment variables:"
    echo "  SERVER_URL - Your Replit deployment URL"
    echo "  ADMIN_KEY  - Admin key from Replit Secrets"
    exit 1
fi

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  NexMDM Device Setup & Enrollment${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}Device:${NC} $DEVICE_ALIAS"
echo -e "${YELLOW}Server:${NC} $SERVER_URL"
echo -e "${YELLOW}Unity Package:${NC} $UNITY_PACKAGE"
echo ""

# Check ADB connection
echo -e "${BLUE}[1/5]${NC} Checking ADB connection..."
adb devices | grep -q "device$"
if [ $? -ne 0 ]; then
    echo -e "${RED}✗ No ADB device connected${NC}"
    echo "Connect your device and enable USB debugging"
    exit 1
fi
echo -e "${GREEN}✓ ADB device connected${NC}"
echo ""

# Step 1: Device optimization (user's existing command)
echo -e "${BLUE}[2/5]${NC} Optimizing device settings and removing bloatware..."
adb shell "settings put global window_animation_scale 0.5; settings put global transition_animation_scale 0.5; settings put global animator_duration_scale 0.5; settings put global ambient_tilt_to_wake 1; settings put global ambient_touch_to_wake 1; settings put global app_standby_enabled 0; settings put global battery_tip_constants app_restriction_enabled=false; pm disable-user --user 0 com.vzw.hss.myverizon; pm disable-user --user 0 com.vzw.apnlib; pm disable-user --user 0 com.verizon.mips.services; pm disable-user --user 0 com.vcast.mediamanager; pm disable-user --user 0 com.reliancecommunications.vvmclient; pm disable-user --user 0 com.google.android.apps.youtube.music; pm disable-user --user 0 com.google.android.youtube; pm disable-user --user 0 com.google.android.apps.videos; pm disable-user --user 0 com.google.android.apps.docs; pm disable-user --user 0 com.google.android.apps.maps; pm disable-user --user 0 com.google.android.apps.photos; pm disable-user --user 0 com.google.android.apps.wallpaper; pm disable-user --user 0 com.google.android.apps.walletnfcrel; pm disable-user --user 0 com.google.android.apps.nbu.files; pm disable-user --user 0 com.google.android.apps.keep; pm disable-user --user 0 com.google.android.apps.googleassistant; pm disable-user --user 0 com.google.android.apps.tachyon; pm disable-user --user 0 com.google.android.apps.safetyhub; pm disable-user --user 0 com.google.android.apps.nbu.paisa.user; pm disable-user --user 0 com.google.android.apps.chromecast.app; pm disable-user --user 0 com.google.android.deskclock; pm disable-user --user 0 com.google.android.calendar; pm disable-user --user 0 com.google.android.gm; pm disable-user --user 0 com.google.android.calculator; pm disable-user --user 0 com.google.android.projection.gearhead; pm disable-user --user 0 com.LogiaGroup.LogiaDeck; pm disable-user --user 0 com.dti.folderlauncher; pm disable-user --user 0 com.huub.viper; pm disable-user --user 0 us.sliide.viper; pm disable-user --user 0 com.example.sarswitch; pm disable-user --user 0 com.android.egg; pm disable-user --user 0 com.android.dreams.basic; pm disable-user --user 0 com.android.dreams.phototable; pm disable-user --user 0 com.android.musicfx; pm disable-user --user 0 com.android.soundrecorder; pm disable-user --user 0 com.android.protips; pm disable-user --user 0 com.android.wallpapercropper; pm disable-user --user 0 com.android.wallpaper.livepicker; pm disable-user --user 0 com.android.providers.partnerbookmarks; pm disable-user --user 0 com.handmark.expressweather; pm disable-user --user 0 com.facebook.katana; pm disable-user --user 0 com.facebook.appmanager; pm disable-user --user 0 com.discounts.viper; pm disable-user --user 0 com.vzw.hss.myverizon.gameshub; pm disable-user --user 0 com.google.android.cellbroadcastreceiver; pm disable-user --user 0 com.android.cellbroadcastreceiver; pm uninstall -k --user 0 com.tripledot.solitaire; pm uninstall -k --user 0 com.vitastudio.mahjong; pm uninstall -k --user 0 com.block.juggle; pm uninstall -k --user 0 com.king.candycrushsaga; pm uninstall -k --user 0 com.king.candycrushsodasaga; pm uninstall -k --user 0 com.superplaystudios.dicedreams; pm uninstall -k --user 0 net.peakgames.toonblast; pm uninstall -k --user 0 com.staplegames.dice; pm uninstall -k --user 0 in.playsimple.tripcross; pm uninstall -k --user 0 com.easybrain.hidden.spots; pm uninstall -k --user 0 com.easybrain.sudoku.android; pm uninstall -k --user 0 com.easybrain.art.puzzle; pm uninstall -k --user 0 net.peakgames.amy; pm uninstall -k --user 0 air.com.buffalo_studios.newflashbingo; pm uninstall -k --user 0 com.tripledot.woodoku; pm uninstall -k --user 0 com.colorwood.jam; pm uninstall -k --user 0 com.cardgame.spades.free; pm uninstall -k --user 0 com.soulcompany.bubbleshooter.relaxing; pm enable com.verizon.dmclientupdate; pm enable com.verizon.obdm; pm enable com.verizon.obdm_permissions; settings put global install_non_market_apps 1"

echo -e "${GREEN}✓ Device optimization complete${NC}"
echo ""

# Step 2: Download APK
echo -e "${BLUE}[3/5]${NC} Downloading NexMDM APK from server..."
APK_FILE="/tmp/nexmdm_${DEVICE_ALIAS}.apk"
curl -f -L -o "$APK_FILE" "${SERVER_URL}/download/nexmdm.apk"
if [ $? -ne 0 ]; then
    echo -e "${RED}✗ Failed to download APK from server${NC}"
    echo "Please ensure the APK is available at: ${SERVER_URL}/download/nexmdm.apk"
    exit 1
fi
echo -e "${GREEN}✓ APK downloaded successfully${NC}"
echo ""

# Step 3: Install APK
echo -e "${BLUE}[4/5]${NC} Installing NexMDM app on device..."
adb install -r "$APK_FILE"
if [ $? -ne 0 ]; then
    echo -e "${RED}✗ Failed to install APK${NC}"
    exit 1
fi
echo -e "${GREEN}✓ NexMDM app installed${NC}"
rm -f "$APK_FILE"
echo ""

# Step 4: Register device with backend
echo -e "${BLUE}[5/5]${NC} Enrolling device with NexMDM server..."
RESPONSE=$(curl -s -X POST "$SERVER_URL/v1/register?alias=$DEVICE_ALIAS" \
    -H "X-Admin: $ADMIN_KEY")

DEVICE_TOKEN=$(echo $RESPONSE | grep -o '"device_token":"[^"]*' | cut -d'"' -f4)
DEVICE_ID=$(echo $RESPONSE | grep -o '"device_id":"[^"]*' | cut -d'"' -f4)

if [ -z "$DEVICE_TOKEN" ]; then
    echo -e "${RED}✗ Failed to register device${NC}"
    echo "Response: $RESPONSE"
    exit 1
fi

echo -e "${GREEN}✓ Device registered with server${NC}"
echo -e "  ${YELLOW}Device ID:${NC} $DEVICE_ID"
echo -e "  ${YELLOW}Token:${NC} ${DEVICE_TOKEN:0:20}..."
echo ""

# Step 5: Send configuration to device via broadcast
echo -e "${BLUE}Sending credentials to device...${NC}"
adb shell am broadcast \
    -a com.nexmdm.CONFIGURE \
    --es server_url "$SERVER_URL" \
    --es token "$DEVICE_TOKEN" \
    --es alias "$DEVICE_ALIAS" \
    --es unity_package "$UNITY_PACKAGE"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Credentials sent to device${NC}"
else
    echo -e "${RED}✗ Failed to send credentials${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✅ Setup & Enrollment Complete!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}Device:${NC} $DEVICE_ALIAS (ID: $DEVICE_ID)"
echo -e "${YELLOW}Server:${NC} $SERVER_URL"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo "1. Grant Usage Access permission:"
echo "   Settings > Apps > Special access > Usage access > NexMDM"
echo ""
echo "2. Grant Notification Listener permission:"
echo "   Settings > Apps > Special access > Notification access > NexMDM"
echo ""
echo "3. Device will start sending heartbeats every 2 minutes"
echo ""
echo -e "${GREEN}Check your dashboard to see the device status!${NC}"
echo ""
