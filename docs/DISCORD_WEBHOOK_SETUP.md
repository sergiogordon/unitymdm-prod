# Discord Webhook Setup Guide

This guide will help you set up Discord webhook integration for NexMDM alerts, including the new service monitoring alerts.

## Prerequisites

- A Discord server where you have admin permissions
- Access to Replit Secrets for your deployment

## Step 1: Create a Discord Webhook

1. Open your Discord server
2. Go to **Server Settings** (click the dropdown next to your server name)
3. Navigate to **Integrations** → **Webhooks**
4. Click **New Webhook** button
5. Configure your webhook:
   - **Name**: "NexMDM Alerts" (or your preferred name)
   - **Channel**: Select the channel where you want alerts to appear
   - **Avatar**: Optionally upload a custom icon
6. Click **Copy Webhook URL**

The webhook URL will look like:
```
https://discord.com/api/webhooks/1234567890/AbCdEfGhIjKlMnOpQrStUvWxYz
```

## Step 2: Add Webhook to Replit Secrets

1. Open your Replit project
2. Click the **Secrets** tool (lock icon in the sidebar)
3. Click **+ New Secret**
4. Configure the secret:
   - **Key**: `DISCORD_WEBHOOK_URL`
   - **Value**: Paste the webhook URL you copied
5. Click **Add Secret**

## Step 3: Restart Your Backend

After adding the secret, restart your backend workflow to load the new environment variable:

1. Go to the Workflows section
2. Stop and restart the "Backend" workflow

Alternatively, the backend will automatically pick up the secret on next restart.

## Step 4: Test the Integration

1. Open your dashboard
2. Click **Settings** (gear icon in header)
3. In the Discord section, click **Send Test Alert**
4. Check your Discord channel for the test message

You should see a message like:
```
🚨 Alert: Test
Device: Test Device
Severity: INFO
Your NexMDM Discord integration is working correctly!
```

## Alert Types

Once configured, you'll receive Discord alerts for:

### 1. Device Offline
Triggered when a device hasn't sent a heartbeat for > threshold time (default: 10 minutes)

**Fields:**
- Device name and ID
- Last seen timestamp
- Offline duration
- Battery level and network type (if available)

### 2. Low Battery
Triggered when device battery drops below threshold (default: 15%)

**Fields:**
- Device name and ID
- Current battery percentage
- Charging status
- Network type

### 3. Unity Down (Legacy)
Triggered when Unity app is not running

**Fields:**
- Device name and ID
- Unity version
- Last seen timestamp

### 4. Service Down (NEW)
Triggered when monitored service hasn't been in foreground for > threshold

**Fields:**
- Device name and ID
- **Service name** (e.g., "Speedtest" or "Unity")
- **Package name** (e.g., "io.unitynodes.unityapp")
- **Last foreground time** (e.g., "15 minutes ago")
- **Threshold** (configured per-device, default: 10 minutes)
- Last seen timestamp

### Recovery Alerts
For all alert types, you'll also receive a recovery notification when the condition resolves:

```
✅ Recovered: Service Down
Device: Device-001
Status: Recovered
```

## Alert Configuration

You can customize alert behavior with these environment variables (optional):

### Alert Cooldowns
```bash
ALERT_DEVICE_COOLDOWN_MIN=30  # Minimum time between alerts for same device/condition
```

After an alert is sent, the same alert won't fire again for 30 minutes (prevents spam).

### Global Rate Limiting
```bash
ALERT_GLOBAL_CAP_PER_MIN=60  # Maximum alerts per minute across all devices
```

Prevents flooding Discord channel with too many alerts at once.

### Roll-up Alerts
When >= 10 devices trigger the same condition within 1 minute, a single "mass alert" is sent instead of individual messages:

```
🚨 Mass Alert: Service Down
15 devices triggered service down condition

Affected Devices (showing 10 of 15):
• Device-001 (12345678...)
• Device-002 (87654321...)
...
```

## Service Monitoring Configuration

To configure which service to monitor per device:

### Via API
```bash
curl -X PATCH https://your-replit-url/admin/devices/{device_id}/monitoring \
  -H "Cookie: session_token=YOUR_SESSION" \
  -H "Content-Type: application/json" \
  -d '{
    "monitor_enabled": true,
    "monitored_package": "io.unitynodes.unityapp",
    "monitored_app_name": "Speedtest",
    "monitored_threshold_min": 10
  }'
```

### Via Dashboard (Coming Soon)
Once frontend is implemented:
1. Select a device
2. Open device settings
3. Configure monitoring:
   - Package to monitor (e.g., `io.unitynodes.unityapp`)
   - Display name (e.g., "Speedtest")
   - Threshold in minutes (1-120, default: 10)
   - Enable/disable monitoring

## Troubleshooting

### No alerts appearing in Discord

1. **Check webhook URL is correct:**
   ```bash
   # In Replit Shell
   echo $DISCORD_WEBHOOK_URL
   ```
   
2. **Verify backend has restarted** after adding secret

3. **Send test alert** from dashboard Settings

4. **Check Discord channel permissions:**
   - Webhook must have permission to post in target channel

### Alerts not triggering for service monitoring

1. **Verify monitoring is enabled:**
   ```bash
   curl https://your-replit-url/admin/devices/{device_id}/monitoring
   ```
   
   Should show `"monitor_enabled": true`

2. **Check Android agent is sending foreground data:**
   - Android agent must send `monitored_foreground_recent_s` in heartbeat
   - Requires Android agent update (see MONITORING_IMPLEMENTATION_STATUS.md)

3. **Check alert evaluator logs:**
   ```bash
   grep "monitoring.evaluate" /tmp/logs/backend_*.log
   ```

### Too many alerts

1. **Increase cooldown period:**
   ```bash
   ALERT_DEVICE_COOLDOWN_MIN=60  # 1 hour
   ```

2. **Adjust threshold:**
   - Increase `monitored_threshold_min` from 10 to 20 or 30 minutes

3. **Disable alerts for specific devices:**
   ```bash
   curl -X PATCH https://your-replit-url/admin/devices/{device_id}/monitoring \
     -d '{"monitor_enabled": false}'
   ```

## Best Practices

1. **Use dedicated channel** for alerts to avoid mixing with regular chat
2. **Set up role mentions** for critical alerts (configure in Discord webhook settings)
3. **Configure thresholds appropriately:**
   - Development/testing: 5-10 minutes
   - Production: 10-20 minutes
   - Stable environments: 20-30 minutes
4. **Monitor alert frequency** and adjust cooldowns if needed
5. **Test alerts** after any configuration changes

## Security Notes

- **Never share** your webhook URL publicly (it grants posting access)
- **Rotate webhook** if accidentally exposed (Discord webhook settings → Regenerate)
- **Use Replit Secrets** (not environment variables) to keep webhook URL secure
- **Webhook URLs expire** if server is deleted/rebuilt - update in Secrets if needed

## Advanced: Webhook URL Rotation

If you need to change your webhook URL:

1. Create new webhook in Discord
2. Update `DISCORD_WEBHOOK_URL` in Replit Secrets
3. Restart backend
4. Delete old webhook in Discord (prevents unauthorized use)

## Support

For issues with Discord integration:
- Check backend logs: `/tmp/logs/backend_*.log`
- Search for: `discord.webhook`
- Look for errors in log events

Example log entries:
```json
{"event": "discord.webhook.sent", "device_id": "dev_123", "condition": "service_down"}
{"event": "discord.webhook.failed", "http_code": 404, "reason": "invalid_webhook"}
```
