#!/bin/bash

################################################################################
# NexMDM Zero-Touch Enrollment Script
# Milestone 3 - Production-ready ADB enrollment with enrollment tokens
################################################################################

set -euo pipefail

# Color codes for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Configuration
APK_CACHE_DIR="/tmp/nexmdm-apk"
LOG_DIR="./enroll-logs"
RETRY_ATTEMPTS=3
RETRY_DELAY=2

# Environment variables validation
if [ -z "${BASE_URL:-}" ]; then
    echo -e "${RED}Error: BASE_URL environment variable not set${NC}"
    echo ""
    echo "Set BASE_URL to your server URL:"
    echo "  export BASE_URL=\"https://your-server.com\""
    exit 1
fi

if [ -z "${ENROLL_TOKEN:-}" ]; then
    echo -e "${RED}Error: ENROLL_TOKEN environment variable not set${NC}"
    echo ""
    echo "Generate an enrollment token from your admin dashboard or API:"
    echo "  export ENROLL_TOKEN=\"your-enrollment-token\""
    exit 1
fi

# Validate HTTPS
if [[ ! "$BASE_URL" =~ ^https:// ]]; then
    echo -e "${RED}Error: BASE_URL must use HTTPS for security${NC}"
    echo "Current BASE_URL: $BASE_URL"
    exit 1
fi

# Optional parameters with defaults
ALIAS="${ALIAS:-Device-$(date +%s)}"
UNITY_PKG="${UNITY_PKG:-org.zwanoo.android.speedtest}"

# Create directories
mkdir -p "$APK_CACHE_DIR"
mkdir -p "$LOG_DIR"

# Log file for this enrollment
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/enroll_${ALIAS}_${TIMESTAMP}.log"
CSV_FILE="$LOG_DIR/enrollment_results.csv"
JSON_FILE="$LOG_DIR/enroll_${ALIAS}_${TIMESTAMP}.json"

# Initialize CSV if not exists
if [ ! -f "$CSV_FILE" ]; then
    echo "timestamp,alias,serial,device_id,result,duration_sec,error" > "$CSV_FILE"
fi

# Logging functions
log() {
    echo -e "$1" | tee -a "$LOG_FILE"
}

log_step() {
    local step=$1
    local total=$2
    local message=$3
    log "${CYAN}${BOLD}[Step $step/$total]${NC} $message"
}

log_success() {
    log "${GREEN}✓${NC} $1"
}

log_error() {
    log "${RED}✗${NC} $1"
}

log_warning() {
    log "${YELLOW}⚠${NC} $1"
}

# JSON logging
json_log() {
    local key=$1
    local value=$2
    echo "\"$key\": \"$value\"," >> "$JSON_FILE"
}

# Retry function
retry_command() {
    local cmd="$1"
    local attempt=1
    
    while [ $attempt -le $RETRY_ATTEMPTS ]; do
        if eval "$cmd"; then
            return 0
        fi
        
        if [ $attempt -lt $RETRY_ATTEMPTS ]; then
            log_warning "Attempt $attempt failed, retrying in ${RETRY_DELAY}s..."
            sleep $RETRY_DELAY
        fi
        attempt=$((attempt + 1))
    done
    
    return 1
}

# Start enrollment
START_TIME=$(date +%s)

log ""
log "${BLUE}${BOLD}═══════════════════════════════════════════════════════${NC}"
log "${BLUE}${BOLD}    NexMDM Zero-Touch Enrollment (Milestone 3)${NC}"
log "${BLUE}${BOLD}═══════════════════════════════════════════════════════${NC}"
log ""
log "Alias: ${BOLD}$ALIAS${NC}"
log "Server: ${BOLD}$BASE_URL${NC}"
log "Unity Package: ${BOLD}$UNITY_PKG${NC}"
log "Token: ${BOLD}${ENROLL_TOKEN:0:12}...${NC} (masked)"
log ""

# Initialize JSON log
echo "{" > "$JSON_FILE"
json_log "timestamp" "$(date -Iseconds)"
json_log "alias" "$ALIAS"
json_log "base_url" "$BASE_URL"
json_log "unity_package" "$UNITY_PKG"

# Step 1/7: Check ADB connection
log_step 1 7 "Checking ADB connection..."

if ! command -v adb &> /dev/null; then
    log_error "ADB command not found. Please install Android SDK Platform Tools."
    json_log "result" "error"
    json_log "error" "ADB not installed"
    echo "}" >> "$JSON_FILE"
    exit 1
fi

if ! retry_command "adb devices | grep -q 'device$'"; then
    log_error "No ADB device connected"
    log "Connect your device via USB and enable USB debugging, then run:"
    log "  ${YELLOW}adb devices${NC}"
    json_log "result" "error"
    json_log "error" "No ADB device connected"
    echo "}" >> "$JSON_FILE"
    exit 1
fi

SERIAL=$(adb devices | grep "device$" | head -1 | awk '{print $1}')
log_success "ADB device connected (Serial: $SERIAL)"
json_log "serial" "$SERIAL"

# Get device ID (Android ID)
DEVICE_ID=$(adb shell settings get secure android_id | tr -d '\r')
log "Device ID: $DEVICE_ID"
json_log "device_id" "$DEVICE_ID"

# Step 2/7: Download latest APK
log_step 2 7 "Downloading latest NexMDM APK..."

APK_PATH="$APK_CACHE_DIR/nexmdm-latest.apk"

# Download APK with enrollment token
if ! curl -f -L -H "Authorization: Bearer $ENROLL_TOKEN" \
    -o "$APK_PATH" \
    "$BASE_URL/v1/apk/download/latest" 2>> "$LOG_FILE"; then
    log_error "Failed to download APK"
    json_log "result" "error"
    json_log "error" "APK download failed"
    echo "}" >> "$JSON_FILE"
    exit 1
fi

APK_SIZE=$(ls -lh "$APK_PATH" | awk '{print $5}')
log_success "APK downloaded and cached ($APK_SIZE)"
json_log "apk_path" "$APK_PATH"

# Step 3/7: Install APK
log_step 3 7 "Installing NexMDM APK on device..."

if ! retry_command "adb install -r '$APK_PATH' &>> '$LOG_FILE'"; then
    log_error "APK installation failed"
    json_log "result" "error"
    json_log "error" "APK installation failed"
    echo "}" >> "$JSON_FILE"
    exit 1
fi

log_success "APK installed successfully"

# Step 4/7: Grant runtime permissions
log_step 4 7 "Granting runtime permissions..."

# Essential permissions for MDM functionality
PERMISSIONS=(
    "android.permission.READ_PHONE_STATE"
    "android.permission.ACCESS_FINE_LOCATION"
    "android.permission.ACCESS_COARSE_LOCATION"
    "android.permission.READ_EXTERNAL_STORAGE"
    "android.permission.WRITE_EXTERNAL_STORAGE"
    "android.permission.CAMERA"
    "android.permission.RECORD_AUDIO"
    "android.permission.POST_NOTIFICATIONS"
)

for perm in "${PERMISSIONS[@]}"; do
    adb shell pm grant com.nexmdm "$perm" 2>/dev/null || true
done

log_success "Runtime permissions granted"

# Step 5/7: System optimizations
log_step 5 7 "Applying system optimizations..."

# Disable Doze for NexMDM
adb shell dumpsys deviceidle whitelist +com.nexmdm &>> "$LOG_FILE" || true

# Allow background execution
adb shell appops set com.nexmdm RUN_ANY_IN_BACKGROUND allow &>> "$LOG_FILE" || true

# Disable battery optimization
adb shell dumpsys battery unplug &>> "$LOG_FILE" || true
adb shell settings put global app_standby_enabled 0 &>> "$LOG_FILE" || true

# Reduce animations for faster responsiveness
adb shell settings put global window_animation_scale 0.5 &>> "$LOG_FILE" || true
adb shell settings put global transition_animation_scale 0.5 &>> "$LOG_FILE" || true
adb shell settings put global animator_duration_scale 0.5 &>> "$LOG_FILE" || true

log_success "System optimizations applied"

# Step 6/7: Device Owner provisioning (safe no-op)
log_step 6 7 "Attempting Device Owner provisioning..."

if adb shell dpm set-device-owner com.nexmdm/.NexDeviceAdminReceiver &>> "$LOG_FILE"; then
    log_success "Device Owner status granted"
    json_log "device_owner" "true"
else
    log_warning "Device Owner provisioning skipped (device not factory reset)"
    log "  This is normal for non-factory-reset devices."
    json_log "device_owner" "false"
fi

# Step 7/7: Enroll device with server
log_step 7 7 "Enrolling device with server..."

# Call enrollment endpoint
ENROLL_RESPONSE=$(curl -sf -X POST \
    -H "Authorization: Bearer $ENROLL_TOKEN" \
    "$BASE_URL/v1/enroll?device_id=$DEVICE_ID" 2>> "$LOG_FILE")

if [ -z "$ENROLL_RESPONSE" ]; then
    log_error "Enrollment failed - no response from server"
    json_log "result" "error"
    json_log "error" "No server response"
    echo "}" >> "$JSON_FILE"
    exit 1
fi

# Extract device token from response
DEVICE_TOKEN=$(echo "$ENROLL_RESPONSE" | grep -o '"device_token":"[^"]*' | cut -d'"' -f4 || echo "")

if [ -z "$DEVICE_TOKEN" ] || [ "$DEVICE_TOKEN" = "*** Token already issued, check device configuration ***" ]; then
    log_warning "Device already enrolled (idempotent)"
    DEVICE_TOKEN="<already_configured>"
fi

# Send configuration to device via broadcast
adb shell am broadcast \
    -a com.nexmdm.CONFIGURE \
    -n com.nexmdm/.EnrollmentReceiver \
    --es server_url "$BASE_URL" \
    --es token "$DEVICE_TOKEN" \
    --es alias "$ALIAS" \
    --es unity_package "$UNITY_PKG" &>> "$LOG_FILE"

log_success "Device enrolled and configured"

# Launch the app
adb shell monkey -p com.nexmdm -c android.intent.category.LAUNCHER 1 &>> "$LOG_FILE" || true

# Calculate duration
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

log ""
log "${GREEN}${BOLD}✅ ENROLLMENT COMPLETE${NC}"
log ""
log "Device: ${BOLD}$ALIAS${NC}"
log "Serial: ${BOLD}$SERIAL${NC}"
log "Device ID: ${BOLD}$DEVICE_ID${NC}"
log "Duration: ${BOLD}${DURATION}s${NC}"
log ""
log "Log saved to: ${BOLD}$LOG_FILE${NC}"
log ""
log "${YELLOW}Manual Steps Required:${NC}"
log "1. On device, go to: Settings > Apps > Special Access > Full screen intents"
log "2. Enable ${BOLD}NexMDM${NC}"
log "3. Go to: Settings > Apps > Special Access > Usage Access"
log "4. Enable ${BOLD}NexMDM${NC}"
log ""
log "The device will start sending heartbeats to the server within 2 minutes."
log ""

# Finalize JSON log
json_log "result" "success"
json_log "duration_sec" "$DURATION"
echo "  \"completed\": true" >> "$JSON_FILE"
echo "}" >> "$JSON_FILE"

# Update CSV
echo "$(date -Iseconds),$ALIAS,$SERIAL,$DEVICE_ID,success,$DURATION," >> "$CSV_FILE"

exit 0
