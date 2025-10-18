# Database Migrations Guide

This document explains the NexMDM database migration system built with Alembic.

## Overview

The migration system provides:
- **Versioned schema changes** - Track every database modification
- **Rollback capability** - Revert to any previous schema version
- **Zero-downtime deployments** - Safe schema evolution in production
- **Idempotency guarantees** - Prevent duplicate data under retry scenarios
- **Automated retention** - Clean up old operational data

## Quick Start

### View Current Migration Status
```bash
cd server
alembic current
alembic history
```

### Apply Latest Migrations
```bash
cd server
alembic upgrade head
```

### Rollback Last Migration
```bash
cd server
alembic downgrade -1
```

### Create New Migration
```bash
cd server
alembic revision -m "Add new feature"
# Edit the generated file in alembic/versions/
alembic upgrade head
```

## Migration Workflow

### 1. Make Model Changes
Edit `server/models.py` to add/modify SQLAlchemy models:
```python
class NewTable(Base):
    __tablename__ = "new_table"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # ... add columns
```

### 2. Generate Migration
```bash
cd server
alembic revision --autogenerate -m "Add new_table"
```

### 3. Review Generated Migration
Check `server/alembic/versions/<revision>_add_new_table.py`:
- Verify `upgrade()` creates tables/adds columns correctly
- Verify `downgrade()` safely reverses changes
- Add `server_default` for NOT NULL columns on existing tables

### 4. Test Migration
```bash
# Test upgrade
alembic upgrade head

# Test downgrade (optional but recommended)
alembic downgrade -1
alembic upgrade head
```

### 5. Deploy to Production
Migrations run automatically on application startup (see `server/main.py`).

## Current Schema

### Core Tables
- `users` - System administrators
- `sessions` - User authentication sessions
- `devices` - Registered Android devices
- `enrollment_tokens` - Zero-touch enrollment tokens with scope tracking

### Time-Series Tables (with retention)
- `device_heartbeats` (2-day retention) - Device health metrics
- `fcm_dispatches` (2-day retention) - FCM command tracking
- `apk_download_events` (7-day retention) - APK download audit trail

### APK Management
- `apk_versions` - APK build metadata with CI tracking
- `apk_installations` - Device APK deployment tracking

### Audit Tables
- `device_events` - Device lifecycle events
- `enrollment_events` - Enrollment audit trail
- `commands` - Remote command tracking

## Idempotency Features

### FCM Dispatch Deduplication
```python
from db_utils import record_fcm_dispatch

result = record_fcm_dispatch(
    db, 
    request_id="unique_cmd_id",  # Idempotency key
    device_id="device_001",
    action="ping"
)

if result['created']:
    # First time - FCM message sent
    pass
else:
    # Duplicate - return existing dispatch
    existing_dispatch = result['dispatch']
```

### Heartbeat Time-Bucketing
```python
from db_utils import record_heartbeat_with_bucketing

result = record_heartbeat_with_bucketing(
    db,
    device_id="device_001",
    heartbeat_data={'status': 'ok', 'battery_pct': 85},
    bucket_seconds=10  # 10-second deduplication window
)

# Multiple heartbeats within 10 seconds → only 1 stored
```

## Retention & Cleanup

### Manual Cleanup
```bash
python server/cleanup_job.py
```

### Automated Cleanup (Recommended)
Add to cron or systemd timer:
```bash
# Run daily at 2am
0 2 * * * cd /path/to/nexmdm && python server/cleanup_job.py
```

### Cleanup Policies
- `device_heartbeats`: 2 days (configurable)
- `fcm_dispatches`: 2 days (configurable)
- `apk_download_events`: 7 days (configurable)

## Performance Targets

The schema is optimized for:
- **100+ concurrent devices** ✓
- **Heartbeat writes**: <150ms p95 latency
- **FCM dispatch lookup**: <5ms (indexed by request_id)
- **Heartbeat queries**: <100ms for last 100 records per device
- **Cleanup jobs**: <60s for 2-day retention window

## Index Strategy

### Covering Indexes
- `fcm_dispatches(request_id)` - O(1) idempotency check
- `fcm_dispatches(device_id, sent_at DESC)` - Device command history
- `device_heartbeats(device_id, ts DESC)` - Time-series queries
- `enrollment_tokens(token_hash)` - Unique token lookup

### Composite Indexes
- `apk_download_events(build_id, ts DESC)` - Download audit queries
- `apk_download_events(token_id, ts DESC)` - Token usage tracking

## Troubleshooting

### Migration Fails with "relation already exists"
Table was created outside migration system. Mark as applied:
```bash
alembic stamp head
```

### Migration Fails with "column cannot be null"
Add `server_default` when adding NOT NULL columns:
```python
op.add_column('table', sa.Column('col', sa.String(), 
    nullable=False, server_default='default_value'))
```

### Downgrade Fails
Check downgrade logic matches upgrade. Common issues:
- Dropping columns that don't exist
- Creating constraints that already exist
- Order of operations (drop FKs before tables)

### Performance Issues
1. Check query plans: `EXPLAIN ANALYZE SELECT ...`
2. Verify indexes exist: `\di` in psql
3. Check connection pool settings in `models.py`
4. Monitor cleanup job timing (should be <60s)

## Best Practices

1. **Always test migrations locally first**
2. **Use autogenerate but review carefully**
3. **Add server_default for NOT NULL columns**
4. **Keep migrations small and focused**
5. **Write descriptive migration messages**
6. **Test both upgrade and downgrade**
7. **Never edit applied migrations**
8. **Use transactions (Alembic default)**
9. **Back up database before major changes**
10. **Monitor migration timing in production**

## Testing Migrations

Run the test suite:
```bash
python server/test_idempotency.py
```

Expected output:
```
✓ FCM dispatch idempotency test passed
✓ Heartbeat time-bucketing test passed
✓ Retention cleanup test passed

All tests passed!
```

## Architecture Decisions

### Why Alembic?
- Industry standard for SQLAlchemy migrations
- Reversible migrations with downgrade support
- Autogenerate from models (less manual SQL)
- Python-based (consistent with codebase)

### Why Time-Bucketing for Heartbeats?
- Prevents duplicate heartbeats on retry/network issues
- Reduces storage by ~10x (1 per 10s vs every retry)
- Maintains operational visibility (10s resolution is sufficient)

### Why request_id for FCM Dispatches?
- Guarantees idempotency for admin commands
- Enables safe retry on network failures
- Provides exact-once semantics for critical operations

## Migration History

### v1: Baseline (7ac6ecbe4e31)
- Captured existing schema from create_all() pattern
- Added fcm_dispatches, apk_download_events, device_heartbeats
- Established indexes and constraints

### v2: Schema Enhancements (a43a2b52588a)
- Added enrollment_tokens.scope and last_used_at
- Added apk_versions CI metadata fields
- Created composite indexes for query optimization

## Support

For issues or questions:
1. Check this guide
2. Review test suite in `server/test_idempotency.py`
3. Check Alembic logs for error details
4. Consult SQLAlchemy/Alembic documentation
