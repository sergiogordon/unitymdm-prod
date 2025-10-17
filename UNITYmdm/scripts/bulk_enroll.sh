#!/bin/bash

################################################################################
# NexMDM Bulk Enrollment Script
# Milestone 3 - Supports 20+ devices with parallel processing
################################################################################

set -euo pipefail

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

# Configuration
MAX_PARALLEL=5  # Maximum parallel enrollments
LOG_DIR="./enroll-logs"
SUMMARY_FILE="$LOG_DIR/bulk_enrollment_summary_$(date +%Y%m%d_%H%M%S).txt"

# Validate environment
if [ -z "${BASE_URL:-}" ]; then
    echo -e "${RED}Error: BASE_URL environment variable not set${NC}"
    exit 1
fi

if [ -z "${ADMIN_KEY:-}" ]; then
    echo -e "${RED}Error: ADMIN_KEY environment variable not set${NC}"
    echo "ADMIN_KEY is needed to generate enrollment tokens"
    exit 1
fi

# Check for devices CSV file
DEVICES_CSV="${1:-devices.csv}"

if [ ! -f "$DEVICES_CSV" ]; then
    echo -e "${RED}Error: $DEVICES_CSV not found${NC}"
    echo ""
    echo "Create a $DEVICES_CSV file with format:"
    echo "alias,unity_package"
    echo "RackA-01,org.zwanoo.android.speedtest"
    echo "RackA-02,org.zwanoo.android.speedtest"
    echo "RackB-01,com.unity.app"
    exit 1
fi

mkdir -p "$LOG_DIR"

echo -e "${BLUE}${BOLD}═══════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}${BOLD}    NexMDM Bulk Enrollment (Milestone 3)${NC}"
echo -e "${BLUE}${BOLD}═══════════════════════════════════════════════════════${NC}"
echo ""
echo "Server: ${BOLD}$BASE_URL${NC}"
echo "Devices file: ${BOLD}$DEVICES_CSV${NC}"
echo ""

# Count total devices
TOTAL_DEVICES=$(tail -n +2 "$DEVICES_CSV" | grep -v '^[[:space:]]*$' | wc -l)
echo "Total devices to enroll: ${BOLD}$TOTAL_DEVICES${NC}"
echo ""

# Initialize summary
echo "NexMDM Bulk Enrollment Summary" > "$SUMMARY_FILE"
echo "===============================" >> "$SUMMARY_FILE"
echo "Started: $(date)" >> "$SUMMARY_FILE"
echo "Server: $BASE_URL" >> "$SUMMARY_FILE"
echo "Total devices: $TOTAL_DEVICES" >> "$SUMMARY_FILE"
echo "" >> "$SUMMARY_FILE"

# Tracking
SUCCESS_COUNT=0
FAIL_COUNT=0
START_TIME=$(date +%s)

# Process function for single device
enroll_device() {
    local alias=$1
    local unity_pkg=$2
    local device_num=$3
    
    echo -e "${CYAN}[$device_num/$TOTAL_DEVICES]${NC} Enrolling ${BOLD}$alias${NC}..."
    
    # Generate enrollment token
    local token_response
    token_response=$(curl -sf -X POST \
        -H "X-Admin: $ADMIN_KEY" \
        "$BASE_URL/v1/enrollment-token?alias=$alias&unity_package=$unity_pkg" 2>/dev/null)
    
    if [ -z "$token_response" ]; then
        echo -e "${RED}[$device_num/$TOTAL_DEVICES] ✗${NC} Failed to generate enrollment token for $alias"
        echo "FAILED: $alias - Token generation failed" >> "$SUMMARY_FILE"
        return 1
    fi
    
    local enroll_token
    enroll_token=$(echo "$token_response" | grep -o '"enrollment_token":"[^"]*' | cut -d'"' -f4)
    
    if [ -z "$enroll_token" ]; then
        echo -e "${RED}[$device_num/$TOTAL_DEVICES] ✗${NC} Invalid token response for $alias"
        echo "FAILED: $alias - Invalid token" >> "$SUMMARY_FILE"
        return 1
    fi
    
    # Run enrollment script
    if BASE_URL="$BASE_URL" \
       ENROLL_TOKEN="$enroll_token" \
       ALIAS="$alias" \
       UNITY_PKG="$unity_pkg" \
       ./enroll_device.sh > "$LOG_DIR/${alias}_enroll.log" 2>&1; then
        echo -e "${GREEN}[$device_num/$TOTAL_DEVICES] ✓${NC} $alias enrolled successfully"
        echo "SUCCESS: $alias" >> "$SUMMARY_FILE"
        return 0
    else
        echo -e "${RED}[$device_num/$TOTAL_DEVICES] ✗${NC} $alias enrollment failed (check $LOG_DIR/${alias}_enroll.log)"
        echo "FAILED: $alias - Enrollment script error" >> "$SUMMARY_FILE"
        return 1
    fi
}

# Parallel processing with job control
declare -a PIDS=()
declare -a RESULTS=()
DEVICE_NUM=0

# Read and process devices
tail -n +2 "$DEVICES_CSV" | while IFS=',' read -r alias unity_pkg || [ -n "$alias" ]; do
    # Skip empty lines
    [ -z "$alias" ] && continue
    
    DEVICE_NUM=$((DEVICE_NUM + 1))
    
    # Default unity package if not specified
    unity_pkg=${unity_pkg:-org.zwanoo.android.speedtest}
    
    # Wait if max parallel jobs reached
    while [ ${#PIDS[@]} -ge $MAX_PARALLEL ]; do
        for i in "${!PIDS[@]}"; do
            if ! kill -0 "${PIDS[$i]}" 2>/dev/null; then
                wait "${PIDS[$i]}" && SUCCESS_COUNT=$((SUCCESS_COUNT + 1)) || FAIL_COUNT=$((FAIL_COUNT + 1))
                unset 'PIDS[$i]'
            fi
        done
        PIDS=("${PIDS[@]}")  # Re-index array
        sleep 0.5
    done
    
    # Start enrollment in background
    enroll_device "$alias" "$unity_pkg" "$DEVICE_NUM" &
    PIDS+=($!)
done

# Wait for remaining jobs
for pid in "${PIDS[@]}"; do
    wait "$pid" && SUCCESS_COUNT=$((SUCCESS_COUNT + 1)) || FAIL_COUNT=$((FAIL_COUNT + 1))
done

# Calculate metrics
END_TIME=$(date +%s)
TOTAL_DURATION=$((END_TIME - START_TIME))
AVG_TIME=$((TOTAL_DURATION / TOTAL_DEVICES))

# Final summary
echo ""
echo -e "${BLUE}${BOLD}═══════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}${BOLD}    Bulk Enrollment Complete${NC}"
echo -e "${BLUE}${BOLD}═══════════════════════════════════════════════════════${NC}"
echo ""
echo "Total devices: ${BOLD}$TOTAL_DEVICES${NC}"
echo "Successful: ${GREEN}${BOLD}$SUCCESS_COUNT${NC}"
echo "Failed: ${RED}${BOLD}$FAIL_COUNT${NC}"
echo "Total duration: ${BOLD}${TOTAL_DURATION}s${NC}"
echo "Average per device: ${BOLD}${AVG_TIME}s${NC}"
echo ""
echo "Summary saved to: ${BOLD}$SUMMARY_FILE${NC}"
echo "Individual logs in: ${BOLD}$LOG_DIR/${NC}"
echo ""

# Append final stats to summary
echo "" >> "$SUMMARY_FILE"
echo "Results:" >> "$SUMMARY_FILE"
echo "--------" >> "$SUMMARY_FILE"
echo "Total: $TOTAL_DEVICES" >> "$SUMMARY_FILE"
echo "Successful: $SUCCESS_COUNT" >> "$SUMMARY_FILE"
echo "Failed: $FAIL_COUNT" >> "$SUMMARY_FILE"
echo "Total duration: ${TOTAL_DURATION}s" >> "$SUMMARY_FILE"
echo "Average per device: ${AVG_TIME}s" >> "$SUMMARY_FILE"
echo "Completed: $(date)" >> "$SUMMARY_FILE"

# Exit with error if any enrollments failed
if [ $FAIL_COUNT -gt 0 ]; then
    exit 1
fi

exit 0
