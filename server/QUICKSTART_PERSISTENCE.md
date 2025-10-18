# Persistence Layer Quick Start

This guide helps you quickly get started with the new persistence features.

## Verification

Verify everything is set up correctly:
```bash
python server/validate_schema.py
```

Expected output:
```
✅ Schema validation passed!
```

## Using the New Features

### 1. Record FCM Dispatch (with idempotency)

In your FCM command handler:
```python
from db_utils import record_fcm_dispatch
import uuid

# Generate unique request_id
request_id = f"cmd_{uuid.uuid4()}"

# Record dispatch (idempotent - duplicates return existing)
result = record_fcm_dispatch(
    db,
    request_id=request_id,
    device_id="device_001",
    action="ping",
    payload_hash="abc123",
    fcm_status="pending"
)

if result['created']:
    # First time - send FCM
    send_fcm_message(...)
else:
    # Duplicate request - return cached result
    return result['dispatch']
```

### 2. Record Heartbeat (with time-bucketing)

In your `/v1/heartbeat` endpoint:
```python
from db_utils import record_heartbeat_with_bucketing

# Store heartbeat with 10-second deduplication
result = record_heartbeat_with_bucketing(
    db,
    device_id="device_001",
    heartbeat_data={
        'status': 'ok',
        'battery_pct': 85,
        'plugged': True,
        'network_type': 'wifi',
        'agent_version': '1.0.5'
    },
    bucket_seconds=10  # Max 1 heartbeat per 10 seconds
)

# result['created'] is False if within same 10s bucket
```

### 3. Record APK Download

In your `/v1/apk/download/latest` endpoint:
```python
from db_utils import record_apk_download

# Log download event for audit
record_apk_download(
    db,
    build_id=latest_build.id,
    source='enrollment',  # or 'manual' or 'ci'
    token_id=enrollment_token.token_id,
    ip=request.client.host
)
```

### 4. Run Cleanup Job

Schedule this in cron:
```bash
# Run daily at 2am
0 2 * * * cd /path/to/nexmdm && python server/cleanup_job.py >> /var/log/nexmdm-cleanup.log 2>&1
```

Or run manually:
```bash
python server/cleanup_job.py
```

## Migration Commands

### Apply migrations
```bash
cd server
alembic upgrade head
```

### Check current version
```bash
alembic current
```

### View migration history
```bash
alembic history
```

### Rollback last migration
```bash
alembic downgrade -1
```

### Create new migration
```bash
# Auto-generate from model changes
alembic revision --autogenerate -m "Add new feature"

# Review the generated file
# Edit server/alembic/versions/<revision>_add_new_feature.py

# Apply it
alembic upgrade head
```

## Performance Monitoring

The db_utils functions log all operations:
```
db_operation event=create entity=fcm_dispatches keys={'request_id': 'cmd_123'} latency_ms=15.3
db_operation event=idempotency_hit entity=fcm_dispatches keys={'request_id': 'cmd_123'} latency_ms=2.1
db_operation event=dedup_hit entity=device_heartbeats keys={'device_id': 'dev_001'} latency_ms=8.7
db_operation event=cleanup entity=device_heartbeats keys={'deleted': 15234} latency_ms=412.5
```

Monitor these logs for:
- High latency warnings (>150ms for heartbeats)
- Idempotency hit rates (should be low, <5%)
- Cleanup job performance (should complete <60s)

## Troubleshooting

### Schema out of sync
```bash
alembic upgrade head
```

### Migration conflicts
```bash
alembic current
alembic history
# Check which migrations are applied
```

### Performance issues
1. Check indexes: `python server/validate_schema.py`
2. Monitor cleanup job timing
3. Review query plans in PostgreSQL

## Next Steps

1. ✅ Schema validated
2. ⏭️ Integrate `db_utils` into backend endpoints
3. ⏭️ Schedule `cleanup_job.py` in production cron
4. ⏭️ Add monitoring for latency metrics
5. ⏭️ Test with 100+ devices to validate performance targets

## Files Reference

- `server/db_utils.py` - Idempotency and cleanup functions
- `server/cleanup_job.py` - Retention cleanup script
- `server/validate_schema.py` - Schema validation
- `server/MIGRATIONS.md` - Comprehensive migration guide
- `server/IMPLEMENTATION_SUMMARY.md` - Full implementation details

## Quick Reference

| Function | Purpose | Idempotency |
|----------|---------|-------------|
| `record_fcm_dispatch()` | Log FCM sends | ✅ request_id |
| `record_heartbeat_with_bucketing()` | Store heartbeats | ✅ 10s buckets |
| `record_apk_download()` | Audit APK downloads | ➖ |
| `cleanup_old_heartbeats()` | Delete old heartbeats | ➖ |
| `cleanup_old_fcm_dispatches()` | Delete old FCM records | ➖ |
| `run_all_retention_cleanups()` | Batch cleanup | ➖ |
