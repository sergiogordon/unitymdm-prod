# Alert System Configuration Guide

## Overview

The MDM alert system provides real-time monitoring and notifications for critical device health conditions. It features intelligent deduplication, rate limiting, roll-up alerts for mass events, and optional auto-remediation.

## Alert Conditions

### 1. Offline Alert (CRIT)
- **Trigger**: No heartbeat received for >20 minutes
- **Severity**: CRITICAL
- **Auto-remediation**: Sends FCM ping (if enabled)

### 2. Low Battery Alert (WARN)
- **Trigger**: Battery level <15%
- **Severity**: WARNING
- **Auto-remediation**: None (alert only)

### 3. Unity Down Alert (CRIT)
- **Trigger**: Unity app not running
- **Severity**: CRITICAL
- **Auto-remediation**: Sends FCM launch_app command (if enabled)

## Configuration

All settings are configured via environment variables:

### Alert Thresholds

```bash
# Offline detection threshold in minutes (default: 20)
ALERT_OFFLINE_MINUTES=20

# Low battery percentage threshold (default: 15)
ALERT_LOW_BATTERY_PCT=15

# Require consecutive heartbeats before alerting for Unity down (default: false)
UNITY_DOWN_REQUIRE_CONSECUTIVE=false
```

### Deduplication & Rate Limiting

```bash
# Per-device cooldown period in minutes (default: 30)
ALERT_DEVICE_COOLDOWN_MIN=30

# Global alert cap per minute (default: 60)
ALERT_GLOBAL_CAP_PER_MIN=60

# Number of devices triggering same condition before roll-up (default: 10)
ALERT_ROLLUP_THRESHOLD=10
```

### Auto-Remediation

```bash
# Enable auto-remediation (default: false)
ALERTS_ENABLE_AUTOREMEDIATION=false
```

**IMPORTANT**: Auto-remediation is OFF by default. When enabled:
- **Offline devices**: Sends FCM ping to wake device
- **Unity down**: Sends FCM launch_app command to restart the monitored app
- All FCM commands are HMAC-signed for security

### Discord Webhook

```bash
# Discord webhook URL for alert notifications
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/your-webhook-url
```

To set up Discord notifications:
1. Go to your Discord server settings → Integrations → Webhooks
2. Create a new webhook
3. Copy the webhook URL
4. Add it to your Replit Secrets as `DISCORD_WEBHOOK_URL`

## Alert Features

### Deduplication
- Prevents duplicate alerts for the same device/condition within the cooldown period
- Tracks alert state per device in the database
- Logs suppressed alerts with `alert.dedupe.hit` event

### Rate Limiting
- Global burst cap prevents alert storms (60/minute by default)
- Protects Discord webhook from rate limit errors
- Logs suppressed alerts with `alert.rate_limited` event

### Roll-up Alerts
- When >10 devices trigger the same condition within 60 seconds, sends one summary alert
- Lists up to 20 affected devices
- Shows "and N more..." for additional devices
- Prevents notification fatigue during mass incidents

### Recovery Notifications
- Automatically sends recovery notification when condition clears
- Tracks self-healed events when auto-remediation succeeds
- No duplicates sent while condition persists

## Discord Alert Format

### Individual Alert
```
🚨 Alert: Offline
Severity: CRIT
Device: Device Name
Device ID: abc123...
Last Seen: 15 minutes ago
Battery: 45%
Network: WiFi
[View Device] (link to dashboard)
```

### Roll-up Alert
```
🚨 Mass Alert: Offline
15 devices triggered offline condition

Affected Devices (showing 15 of 15):
• Device-1 (abc123...)
• Device-2 (def456...)
...

[View All Devices] (link to dashboard)
```

### Recovery Alert
```
✅ Recovered: Offline
Device: Device Name
Device ID: abc123...
Status: Recovered
[View Device] (link to dashboard)
```

## Observability

### Events
All alert operations emit structured JSON logs:

```json
{
  "ts": "2025-10-18T12:00:00Z",
  "level": "INFO",
  "event": "alert.raise.offline",
  "device_id": "abc123",
  "alias": "Device-1",
  "severity": "CRIT"
}
```

Event types:
- `alert.evaluate.start/end` - Evaluation cycle
- `alert.raise.{condition}` - Alert raised
- `alert.recover` - Device recovered
- `alert.dedupe.hit` - Duplicate suppressed
- `alert.rate_limited` - Rate limit triggered
- `alert.rollup.sent` - Roll-up alert sent
- `remediation.attempt.success/fail` - Auto-remediation result

### Metrics
Prometheus-compatible metrics exposed at `/metrics`:

- `alerts_sent_total{condition, severity}` - Total alerts sent
- `alerts_suppressed_total{reason, condition}` - Alerts suppressed
- `alerts_recovered_total{condition}` - Recovery notifications
- `remediations_attempted_total{action}` - Remediation attempts
- `remediations_success_total{action}` - Successful remediations
- `remediations_failed_total{action, reason}` - Failed remediations
- `alert_evaluation_latency_ms` - Evaluation duration
- `discord_webhook_latency_ms` - Webhook send time

## Performance Targets

- **Evaluation**: <200ms for 1000 devices
- **Webhook dispatch**: p95 <300ms
- **FCM enqueue**: p95 <200ms
- **Evaluation frequency**: Every 60 seconds

Current performance (11 devices): ~800ms evaluation time

## Testing

### Test Discord Integration
```bash
curl -X POST http://localhost:8000/v1/test-alert \
  -H "X-Admin: your-admin-key"
```

### Monitor Logs
Structured logs show all alert activity:
```bash
# View alert scheduler logs
grep "alert\." /tmp/logs/Backend*.log

# View remediation attempts
grep "remediation\." /tmp/logs/Backend*.log
```

### Check Metrics
```bash
curl http://localhost:8000/metrics | grep alerts
```

## Security

- Discord webhook URL stored as secret, never logged
- All FCM commands HMAC-signed with HMAC_SECRET
- Invalid HMAC signatures rejected at device level
- No secrets exposed in alert messages or logs

## Troubleshooting

### Alerts not sending
1. Check `DISCORD_WEBHOOK_URL` is configured
2. Verify webhook URL is valid (test with `/v1/test-alert`)
3. Check logs for `discord.webhook.failed` events

### Too many alerts
1. Increase `ALERT_DEVICE_COOLDOWN_MIN` (default: 30)
2. Lower `ALERT_GLOBAL_CAP_PER_MIN` (default: 60)
3. Adjust `ALERT_ROLLUP_THRESHOLD` (default: 10)

### Auto-remediation not working
1. Verify `ALERTS_ENABLE_AUTOREMEDIATION=true`
2. Check device has FCM token registered
3. Verify `HMAC_SECRET` is configured
4. Check logs for `remediation.attempt` events

### False positives
1. Increase thresholds (e.g., `ALERT_OFFLINE_MINUTES=15`)
2. Enable consecutive checks for Unity (`UNITY_DOWN_REQUIRE_CONSECUTIVE=true`)
3. Verify device heartbeat intervals align with thresholds

## Architecture

```
┌─────────────────┐
│ Alert Scheduler │ (runs every 60s)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Alert Evaluator │ (checks all devices for conditions)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Alert Manager  │ (dedup, rate limit, roll-up)
└────────┬────────┘
         │
         ├──────► Discord Webhook (notifications)
         │
         └──────► Auto Remediation (FCM commands)
```

## Database Schema

```sql
CREATE TABLE alert_states (
  id INTEGER PRIMARY KEY,
  device_id VARCHAR NOT NULL,
  condition VARCHAR NOT NULL,
  state VARCHAR NOT NULL DEFAULT 'ok',
  last_raised_at TIMESTAMP,
  last_recovered_at TIMESTAMP,
  cooldown_until TIMESTAMP,
  consecutive_violations INTEGER DEFAULT 0,
  last_value VARCHAR,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL,
  UNIQUE(device_id, condition)
);
```

## Best Practices

1. **Start with defaults**: Test with default settings before tuning
2. **Monitor metrics**: Use Prometheus metrics to track alert volume
3. **Gradual rollout**: Enable auto-remediation on a few devices first
4. **Review logs**: Check structured logs for patterns
5. **Tune thresholds**: Adjust based on your fleet's behavior
6. **Test recovery**: Verify recovery alerts work correctly
7. **Discord rate limits**: Discord allows ~30 messages/minute per webhook

## Example Configuration

```bash
# Production-ready configuration for 100+ devices
ALERT_OFFLINE_MINUTES=20
ALERT_LOW_BATTERY_PCT=15
ALERT_DEVICE_COOLDOWN_MIN=30
ALERT_GLOBAL_CAP_PER_MIN=60
ALERT_ROLLUP_THRESHOLD=10
ALERTS_ENABLE_AUTOREMEDIATION=true
UNITY_DOWN_REQUIRE_CONSECUTIVE=true
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```
