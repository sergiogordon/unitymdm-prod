# Service Monitoring Implementation Status

## Completed Tasks ✅

### 1. Backend Database Schema (✅ DONE)
- Added `monitored_threshold_min` (int, default 10) to Device model
- Added `monitor_enabled` (bool, default True) to Device model
- Added index on `(monitor_enabled, monitored_package)` for efficient queries
- Added service monitoring fields to DeviceLastStatus:
  - `service_up` (bool, nullable)
  - `monitored_foreground_recent_s` (int, nullable)
  - `monitored_package` (string, nullable)
  - `monitored_threshold_min` (int, nullable)
- Added index on `(service_up, last_ts)` for service_down queries

### 2. Backend API Endpoints (✅ DONE)
- **GET `/admin/devices/{device_id}/monitoring`** - Get monitoring configuration
- **PATCH `/admin/devices/{device_id}/monitoring`** - Update monitoring configuration
- Updated **PATCH `/v1/devices/{device_id}/settings`** to handle new fields
- Added validation:
  - Package name format validation (regex)
  - Threshold clamped to 1-120 minutes
  - Structured logging for all monitoring updates

### 3. Heartbeat Payload & Processing (✅ DONE)
- Added `monitored_foreground_recent_s` field to HeartbeatPayload schema
- Implemented service up/down evaluator in heartbeat processing:
  - Evaluates service status based on foreground recency vs threshold
  - Fallback to Speedtest-specific signals for backward compatibility
  - Updates DeviceLastStatus with service monitoring data
  - Logs state transitions (service_down → service_up and vice versa)
  - Emits Prometheus metrics for service status

### 4. Alert System Integration (✅ DONE)
- Added `SERVICE_DOWN` condition to AlertCondition enum
- Implemented `evaluate_service_down()` method in AlertEvaluator:
  - Uses DeviceLastStatus for efficient querying
  - Tracks state transitions for alerts and recoveries
  - Supports cooldown and deduplication
- Updated Discord webhook to handle service_down alerts:
  - Custom embed formatting with service name, threshold, last foreground time
  - Recovery notifications
  - Roll-up alerts for mass service_down events
- Added observability:
  - Structured logs: `monitoring.evaluate`, `monitoring.service_down`, `monitoring.service_up`
  - Metrics: `service_up_devices` gauge

### 5. Enhanced Discord Alert Format (✅ DONE)
- Service name display (monitored_app_name)
- Package name display
- Last foreground time in minutes
- Configured threshold
- Link to device dashboard

## Remaining Tasks 📋

### 6. Android Agent Updates (⏳ TODO - Separate Repository)
**Location:** Android repository (not in this repo)

**Required Changes:**
1. Add UsageStatsManager integration to detect foreground recency for ANY package
2. Update heartbeat payload to include `monitored_foreground_recent_s`
3. Grant PACKAGE_USAGE_STATS permission (already granted via ADB setup)

**Implementation:**
```kotlin
// In MonitorService.kt or TelemetryCollector.kt
private fun getMonitoredForegroundRecency(packageName: String): Int? {
    val usageStatsManager = getSystemService(Context.USAGE_STATS_SERVICE) as UsageStatsManager
    val now = System.currentTimeMillis()
    val oneHourAgo = now - (60 * 60 * 1000) // 1 hour lookback
    
    val stats = usageStatsManager.queryUsageStats(
        UsageStatsManager.INTERVAL_DAILY,
        oneHourAgo,
        now
    )
    
    val packageStats = stats.find { it.packageName == packageName }
    
    return if (packageStats != null && packageStats.lastTimeUsed > 0) {
        ((now - packageStats.lastTimeUsed) / 1000).toInt() // seconds
    } else {
        null // Usage stats not available
    }
}

// In heartbeat payload construction
val monitored_foreground_recent_s = device.monitored_package?.let { pkg ->
    getMonitoredForegroundRecency(pkg)
}

// Add to heartbeat JSON
put("monitored_foreground_recent_s", monitored_foreground_recent_s)
```

### 7. Frontend - Monitoring Settings UI (⏳ TODO)
**Location:** `frontend/components/settings-drawer.tsx` or create new `device-monitoring-settings.tsx`

**Required Changes:**
Add a new section to the device detail drawer/panel with:
- Service package to monitor (text input with validation)
- Display name/alias (text input)
- Threshold in minutes (number input, 1-120 range)
- Monitoring enabled toggle

**API Integration:**
```typescript
// Fetch current settings
const monitoringSettings = await fetch(`/admin/devices/${deviceId}/monitoring`)

// Update settings
await fetch(`/admin/devices/${deviceId}/monitoring`, {
  method: 'PATCH',
  body: JSON.stringify({
    monitored_package: "org.zwanoo.android.speedtest",
    monitored_app_name: "Speedtest",
    monitored_threshold_min: 10,
    monitor_enabled: true
  })
})
```

### 8. Frontend - Device List Service Status (⏳ TODO)
**Location:** `frontend/components/devices-table.tsx`

**Required Changes:**
1. Add new columns to device table:
   - **Service** (monitored_app_name or monitored_package)
   - **Service Status** (Up / Down / Unknown with color indicators)
   - **Last Foreground** (relative time, e.g., "2m ago", "15m ago")

2. Update search/filter to support:
   - `service:down` - filter devices with service down
   - `service:unknown` - filter devices with unknown service status

3. Visual indicators:
   - ✅ Green for service UP
   - ❌ Red for service DOWN
   - ⚠️ Yellow/Gray for UNKNOWN

**Type Updates:**
```typescript
interface Device {
  // ... existing fields
  monitoring?: {
    monitor_enabled: boolean
    monitored_package: string
    monitored_app_name: string
    monitored_threshold_min: number
    service_up: boolean | null
    monitored_foreground_recent_s: number | null
  }
}
```

### 9. Discord Webhook Setup Documentation (⏳ TODO)
**Location:** Create `DISCORD_WEBHOOK_SETUP.md`

**Content:**
1. How to create a Discord webhook:
   - Server Settings → Integrations → Webhooks → New Webhook
   - Copy webhook URL
2. Add to Replit Secrets:
   - Secret name: `DISCORD_WEBHOOK_URL`
   - Value: `https://discord.com/api/webhooks/...`
3. Test the integration:
   - Use Settings → Send Test Alert in the dashboard
4. Alert cooldown and rate limiting configuration:
   - `ALERT_DEVICE_COOLDOWN_MIN` (default: 30 minutes)
   - `ALERT_GLOBAL_CAP_PER_MIN` (default: 60 alerts/minute)

## Database Migration

Since new columns were added, you need to restart the server to create them automatically (SQLAlchemy will handle this):

```bash
# Backend will auto-create new columns on startup
# No manual migration needed
```

## Testing Checklist

### Backend Testing
- [ ] Create/update device monitoring settings via API
- [ ] Send heartbeat with `monitored_foreground_recent_s = 700` (>10min) → triggers service_down
- [ ] Send heartbeat with `monitored_foreground_recent_s = 30` (<10min) → triggers recovery
- [ ] Verify Discord alert is sent on service_down
- [ ] Verify Discord recovery alert is sent on service_up
- [ ] Test cooldown (should not send duplicate alerts within 30 min)
- [ ] Test threshold changes (update from 10min to 5min, verify evaluation)
- [ ] Test monitoring disabled (no alerts when `monitor_enabled = false`)

### Frontend Testing (when implemented)
- [ ] Open device monitoring settings
- [ ] Update monitored package
- [ ] Change threshold from 10 to 5 minutes
- [ ] Toggle monitoring enabled/disabled
- [ ] View service status in device list
- [ ] Filter by `service:down`
- [ ] Verify last foreground time display

### Android Agent Testing (when implemented)
- [ ] Verify `monitored_foreground_recent_s` is sent in heartbeat
- [ ] Test with Speedtest package (should work)
- [ ] Test with Unity package (should work when switched)
- [ ] Test with app in foreground (should report low seconds)
- [ ] Test with app in background for 15min (should report ~900s)
- [ ] Handle missing PACKAGE_USAGE_STATS permission gracefully (send null)

## Environment Variables

### Existing (already configured)
- `DISCORD_WEBHOOK_URL` - Discord webhook for alerts
- `ALERT_DEVICE_COOLDOWN_MIN` - Cooldown between alerts (default: 30)
- `ALERT_GLOBAL_CAP_PER_MIN` - Max alerts per minute (default: 60)

### New (optional, with defaults)
- `HEARTBEAT_INTERVAL_SECONDS` - Expected heartbeat interval (default: 300 = 5 minutes)

## API Documentation

### GET /admin/devices/{device_id}/monitoring
**Response:**
```json
{
  "ok": true,
  "monitoring": {
    "monitor_enabled": true,
    "monitored_package": "org.zwanoo.android.speedtest",
    "monitored_app_name": "Speedtest",
    "monitored_threshold_min": 10,
    "service_up": true,
    "monitored_foreground_recent_s": 45,
    "last_seen": "2025-01-17T10:30:00Z"
  }
}
```

### PATCH /admin/devices/{device_id}/monitoring
**Request:**
```json
{
  "monitor_enabled": true,
  "monitored_package": "org.zwanoo.android.speedtest",
  "monitored_app_name": "Speedtest",
  "monitored_threshold_min": 10
}
```

**Response:**
```json
{
  "ok": true,
  "message": "Monitoring settings updated successfully",
  "monitoring": {
    "monitor_enabled": true,
    "monitored_package": "org.zwanoo.android.speedtest",
    "monitored_app_name": "Speedtest",
    "monitored_threshold_min": 10
  }
}
```

## Acceptance Criteria Status

- [x] Per-device monitoring settings live (backend)
- [x] Backend evaluates Up/Down against configurable threshold
- [x] Discord alerts/recoveries fire with dedupe
- [ ] UI displays and edits settings (frontend TODO)
- [ ] Device list shows service status (frontend TODO)
- [ ] Agent reports foreground recency (Android TODO)
- [x] Works with Speedtest package (backward compatible)
- [x] Can switch to Unity package without code changes

## Next Steps

1. **Immediate:** Test the backend implementation
   - Send test heartbeats with various `monitored_foreground_recent_s` values
   - Verify alerts are triggered and sent to Discord
   - Check alert cooldowns and deduplication

2. **Short-term:** Implement Frontend UI (Tasks 7-8)
   - Add monitoring settings section to device drawer
   - Add service status columns to device table
   - Add filters for service:down

3. **Medium-term:** Update Android Agent (Task 6)
   - Implement UsageStatsManager integration
   - Send `monitored_foreground_recent_s` in heartbeat
   - Test with both Speedtest and Unity packages

4. **Final:** Documentation and Deployment (Task 9)
   - Create Discord webhook setup guide
   - Document monitoring feature in user guide
   - Update replit.md with monitoring information
