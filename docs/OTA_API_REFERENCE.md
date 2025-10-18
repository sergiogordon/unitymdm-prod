# OTA Update API Reference

## Quick Reference

### Device Endpoints

#### Check for Updates
```http
GET /v1/agent/update?device_id={id}&current_version_code={code}&package_name={pkg}
Authorization: Bearer {device_token}
```

**Responses:**
- `304 Not Modified` - No update available
- `200 OK` - Update manifest returned

**Update Manifest Schema:**
```json
{
  "build_id": 42,
  "version_code": 200,
  "version_name": "2.0.0",
  "package_name": "com.nexmdm.agent",
  "download_url": "https://.../v1/apk/42/download",
  "sha256": "abc123...",
  "signer_fingerprint": "AA:BB:CC:DD:...",
  "file_size": 8500000,
  "wifi_only": true,
  "must_install": false,
  "staged_rollout_percent": 25,
  "release_notes": "Bug fixes and improvements"
}
```

### Admin Endpoints

#### Promote Build to Current
```http
POST /v1/apk/{build_id}/promote
Authorization: Bearer {admin_token}
Content-Type: application/json

{
  "rollout_percent": 10,
  "wifi_only": true,
  "must_install": false
}
```

**Response:**
```json
{
  "success": true,
  "build_id": 42,
  "version_code": 200,
  "staged_rollout_percent": 10,
  "previous_build_id": 41
}
```

#### Adjust Rollout Percentage
```http
POST /v1/apk/{build_id}/rollout
Authorization: Bearer {admin_token}
Content-Type: application/json

{
  "rollout_percent": 50
}
```

**Response:**
```json
{
  "success": true,
  "build_id": 42,
  "old_percent": 10,
  "new_percent": 50
}
```

#### Rollback to Previous Build
```http
POST /v1/apk/rollback
Authorization: Bearer {admin_token}
Content-Type: application/json

{
  "force_downgrade": true
}
```

**Response:**
```json
{
  "success": true,
  "rolled_back_to": {
    "build_id": 41,
    "version_code": 100,
    "version_name": "1.0.0"
  },
  "rolled_back_from": {
    "build_id": 42,
    "version_code": 200,
    "version_name": "2.0.0"
  },
  "force_downgrade": true
}
```

#### Trigger Update Check (FCM Nudge)
```http
POST /v1/apk/nudge-update
Authorization: Bearer {admin_token}
Content-Type: application/json

{
  "device_ids": ["dev-001", "dev-002"]  // Optional, omit for fleet-wide
}
```

**Response:**
```json
{
  "success": true,
  "total_devices": 100,
  "success_count": 98,
  "failed_count": 2,
  "failed_devices": [
    {
      "device_id": "dev-003",
      "alias": "Device 3",
      "reason": "No FCM token"
    }
  ]
}
```

#### Get Deployment Statistics
```http
GET /v1/apk/{build_id}/deployment-stats
Authorization: Bearer {admin_token}
```

**Response:**
```json
{
  "build_id": 42,
  "total_checks": 1500,
  "total_eligible": 250,
  "total_downloads": 245,
  "installs_success": 240,
  "installs_failed": 5,
  "verify_failed": 0,
  "last_updated": "2025-10-18T19:30:00Z",
  "adoption_rate": 96.0
}
```

## Cohort Logic

### How Device Cohorting Works

Devices are deterministically assigned to cohorts using SHA-256 hashing:

```python
cohort = hash(device_id) % 100  # Returns 0-99
is_eligible = cohort < rollout_percent
```

**Properties:**
- Deterministic (same device always gets same cohort)
- No server-side state required
- Instant rollout adjustments
- Uniform distribution across fleet

**Example:**
- Device "abc123" → cohort 47
- At 25% rollout → NOT eligible (47 >= 25)
- At 50% rollout → eligible (47 < 50)
- At 100% rollout → eligible (47 < 100)

## Staged Rollout Best Practices

### Recommended Rollout Progression

```
1% (Canary)
  ↓ Wait 1-2 hours, monitor metrics
5% (Early Adopters)
  ↓ Wait 30-60 minutes
10% (Validation)
  ↓ Wait 30-60 minutes
25% (Expansion)
  ↓ Wait 1-2 hours
50% (Majority)
  ↓ Wait 1-2 hours
100% (Full Fleet)
```

### Monitoring Checkpoints

At each stage, verify:
- ✅ `verify_failed == 0` (no signature issues)
- ✅ `installs_failed / total_downloads < 2%` (high success rate)
- ✅ `adoption_rate > 90%` (devices actually updating)
- ✅ No spike in device offline events
- ✅ No increase in crash reports

### When to Rollback

Trigger immediate rollback if:
- `verify_failed > 0` (signature mismatch)
- `installs_failed > 10%` of downloads
- User reports of crashes/issues
- Device offline rate increases >20%
- Critical bug discovered

## FCM Update Command

When devices receive FCM "update" command:

```json
{
  "action": "update",
  "request_id": "uuid-here",
  "device_id": "abc123",
  "ts": "2025-10-18T19:30:00Z",
  "hmac": "signature-here"
}
```

Device behavior:
1. Verify HMAC signature
2. Immediately call `/v1/agent/update`
3. If update available, download APK
4. Verify SHA-256 checksum
5. Verify signer fingerprint
6. Check safety constraints (Wi-Fi, battery, disk)
7. Install APK
8. Report result to server

## Safety Constraints

### Wi-Fi Only
When `wifi_only: true`:
- Device MUST be on Wi-Fi to download
- Prevents carrier data overages
- Critical for large APKs (>50MB)

### Must Install
When `must_install: true`:
- Device SHOULD install ASAP
- Can be deferred by safety checks
- Used for critical security updates

### Client-Side Checks
Before installation, device verifies:
- Battery level > 20%
- Available disk space > 500MB
- Not in active phone call
- Connected to Wi-Fi (if wifi_only=true)
- SHA-256 matches manifest
- Signer fingerprint matches expected

## Error Handling

### 304 Not Modified Reasons

Logged in structured events:
```json
{
  "event": "ota.manifest.304",
  "reason": "no_current_build",
  "device_id": "abc123",
  "package_name": "com.nexmdm.agent"
}
```

Possible reasons:
- `no_current_build` - No build promoted yet
- `already_current` - Device on latest version
- `not_in_cohort` - Device not in rollout percentage

### Common Errors

**Build Not Found (404):**
```json
{"detail": "APK not found"}
```

**Not Authorized (403):**
```json
{"detail": "Not authenticated"}
```

**Invalid Rollout Percent (422):**
```json
{"detail": "rollout_percent must be between 0 and 100"}
```

## Metrics & Observability

### Prometheus Metrics

```
# Total update checks
ota_check_total{status="no_update"} 15000
ota_check_total{status="available"} 500

# Downloads by build
ota_download_total{build_id="42",version_code="200"} 480

# Installations
ota_install_total{build_id="42",status="success"} 475
ota_install_total{build_id="42",status="failed"} 5

# Verification failures
ota_verify_failed_total 0

# FCM nudges sent
ota_nudge_total{status="sent"} 100
```

### Structured Log Events

All events logged as JSON:
```json
{"ts": "...", "event": "ota.promote", "build_id": 42, "rollout_percent": 10}
{"ts": "...", "event": "ota.rollout.adjust", "build_id": 42, "old": 10, "new": 25}
{"ts": "...", "event": "ota.rollback", "from_build_id": 42, "to_build_id": 41}
{"ts": "...", "event": "ota.manifest.200", "device_id": "abc", "build_id": 42}
{"ts": "...", "event": "ota.manifest.304", "device_id": "xyz", "reason": "not_in_cohort"}
{"ts": "...", "event": "ota.nudge.sent", "total_devices": 100, "success_count": 98}
```

## Integration Examples

### Python Client (Admin)
```python
import requests

API_URL = "https://your-mdm.com"
TOKEN = "admin-jwt-token"

def promote_build(build_id, rollout_percent=10):
    response = requests.post(
        f"{API_URL}/v1/apk/{build_id}/promote",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={
            "rollout_percent": rollout_percent,
            "wifi_only": True,
            "must_install": False
        }
    )
    return response.json()

def adjust_rollout(build_id, new_percent):
    response = requests.post(
        f"{API_URL}/v1/apk/{build_id}/rollout",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={"rollout_percent": new_percent}
    )
    return response.json()

def rollback():
    response = requests.post(
        f"{API_URL}/v1/apk/rollback",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={"force_downgrade": True}
    )
    return response.json()
```

### Android Client (Device)
```kotlin
fun checkForUpdate() {
    val response = retrofit.get("/v1/agent/update") {
        parameter("device_id", deviceId)
        parameter("current_version_code", BuildConfig.VERSION_CODE)
        parameter("package_name", BuildConfig.APPLICATION_ID)
    }
    
    when (response.code()) {
        304 -> Log.d("OTA", "No update available")
        200 -> {
            val manifest = response.body()
            downloadAndInstall(manifest)
        }
    }
}

suspend fun downloadAndInstall(manifest: UpdateManifest) {
    // 1. Download APK
    val apkFile = downloadApk(manifest.download_url)
    
    // 2. Verify SHA-256
    val actualHash = calculateSHA256(apkFile)
    require(actualHash == manifest.sha256) { "Checksum mismatch" }
    
    // 3. Verify signer
    val actualFingerprint = getSignerFingerprint(apkFile)
    require(actualFingerprint == manifest.signer_fingerprint) { "Signer mismatch" }
    
    // 4. Check constraints
    if (manifest.wifi_only) {
        require(isConnectedToWifi()) { "Wi-Fi required" }
    }
    require(getBatteryLevel() > 20) { "Low battery" }
    require(getAvailableDiskSpace() > 500_000_000) { "Insufficient storage" }
    
    // 5. Install
    installApk(apkFile)
}
```

---

**For more details, see:**
- [MILESTONE_4_OTA_SUMMARY.md](../MILESTONE_4_OTA_SUMMARY.md) - Complete implementation overview
- [replit.md](../replit.md) - System architecture documentation
