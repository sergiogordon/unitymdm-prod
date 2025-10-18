# NexMDM Operations Runbook: Partition Management & Performance

## Quick Reference

### 🚨 Emergency Procedures

| Issue | Quick Fix | Detailed Section |
|-------|-----------|------------------|
| p99 latency spike | Check pool saturation → Kill switch | [Performance Degradation](#performance-degradation) |
| Partition creation failed | Check disk space → Manual create | [Partition Failures](#partition-failures) |
| Archive job stuck | Check advisory lock → Force unlock | [Archive Issues](#archive-issues) |
| Device status drift | Run reconciliation | [Data Consistency](#data-consistency) |

### 📊 Key Performance Targets

- **Heartbeat p95**: <150ms
- **Heartbeat p99**: <300ms
- **Read queries p95**: <20ms
- **DB CPU**: <70%
- **Error rate**: <0.5%
- **Data loss**: 0

---

## System Architecture

### Components

1. **device_heartbeats** - Partitioned by day (90 days retention)
2. **device_last_status** - Fast-read table with O(1) lookups
3. **hb_partitions** - Metadata tracking partition lifecycle
4. **Dual-write system** - Ensures consistency between heartbeats and last_status
5. **Reconciliation job** - Hourly consistency repair (last 24h)
6. **Nightly maintenance** - Partition creation, archival, pruning, VACUUM

### Data Flow

```
Device Heartbeat
    ↓
Deduplication (10s bucketing)
    ↓
├─→ device_heartbeats (partitioned, historical)
└─→ device_last_status (fast reads, current)
    ↓
Read queries (if READ_FROM_LAST_STATUS=true)
```

---

## Operational Procedures

### Daily Operations

#### 1. Morning Health Check

```bash
# Check partition count (should be ~105)
psql $DATABASE_URL -c "SELECT COUNT(*) FROM hb_partitions WHERE state='active';"

# Verify recent partitions exist
psql $DATABASE_URL -c "SELECT partition_name, row_count, pg_size_pretty(bytes_size) 
FROM hb_partitions WHERE range_start >= NOW() - INTERVAL '7 days' ORDER BY range_start DESC;"

# Check last reconciliation run
grep "reconciliation.completed" /tmp/logs/backend_*.log | tail -1
```

#### 2. Metrics Review

Access metrics endpoint (requires ADMIN_KEY):
```bash
curl -H "x-admin: $ADMIN_KEY" https://your-domain.repl.co/metrics
```

Key metrics to monitor:
- `heartbeats_ingested_total` - Should be steady
- `reconciliation_rows_updated_total` - Should be low (<100/hr)
- `partitions_created_total` - Should increment daily
- `archive_failures_total` - Should be 0
- `http_request_latency_ms_bucket` - Check p95/p99

### Scheduled Jobs Setup

#### Option 1: UptimeRobot (Recommended)

1. Create monitor: `https://your-domain.repl.co/ops/nightly`
2. Type: HTTP(s) - Keyword
3. Interval: Every 24 hours (3:00 AM UTC)
4. Custom HTTP Headers:
   ```
   x-admin: YOUR_ADMIN_KEY
   ```
5. Request Method: POST

Repeat for `/ops/reconcile` with 1-hour interval.

#### Option 2: Cron-job.org

1. URL: `https://your-domain.repl.co/ops/nightly`
2. Schedule: `0 3 * * *` (daily at 3 AM)
3. Request Method: POST
4. Headers: `x-admin: YOUR_ADMIN_KEY`

### Manual Job Execution

```bash
# Dry-run nightly maintenance
cd server && python nightly_maintenance.py --dry-run

# Execute nightly maintenance
cd server && python nightly_maintenance.py --retention-days 90

# Run reconciliation
cd server && python reconciliation_job.py

# Backfill device_last_status
cd server && python backfill_last_status.py --days 7
```

---

## Partition Management

### Manual Partition Creation

If nightly job fails to create future partitions:

```bash
cd server && python -c "
from db_utils import create_heartbeat_partition
from datetime import date, timedelta

# Create next 14 days
for i in range(14):
    target = date.today() + timedelta(days=i)
    create_heartbeat_partition(target)
    print(f'Created partition for {target}')
"
```

### Partition Inspection

```sql
-- View partition metadata
SELECT 
    partition_name,
    state,
    row_count,
    pg_size_pretty(bytes_size) as size,
    range_start,
    range_end
FROM hb_partitions
ORDER BY range_start DESC
LIMIT 20;

-- Check partition health
SELECT 
    state,
    COUNT(*) as count,
    pg_size_pretty(SUM(bytes_size)) as total_size
FROM hb_partitions
GROUP BY state;

-- Find partitions with no data
SELECT partition_name, range_start
FROM hb_partitions
WHERE row_count = 0 AND state = 'active'
ORDER BY range_start DESC;
```

### Partition Archival

Archive process (automated, but can be manual):

```sql
-- Mark partition for archival
UPDATE hb_partitions
SET state = 'active'  -- Will be picked up next maintenance run
WHERE partition_name = 'device_heartbeats_YYYYMMDD';

-- Check archive status
SELECT partition_name, state, archived_at, checksum_sha256
FROM hb_partitions
WHERE state IN ('archived', 'archive_failed')
ORDER BY archived_at DESC;
```

### Retention Adjustment

To change retention from 90 to 60 days:

```bash
# Update nightly job
cd server && python nightly_maintenance.py --retention-days 60

# Update external scheduler configuration
# (UptimeRobot/Cronjob.org to pass retention_days=60 parameter)
```

---

## Feature Flag Management

### Enabling Fast Reads

1. **Backfill first** (critical!):
   ```bash
   cd server && python backfill_last_status.py --days 7
   ```

2. **Enable flag**:
   ```bash
   # In Replit Secrets
   READ_FROM_LAST_STATUS=true
   ```

3. **Monitor for 24h**:
   ```bash
   # Check performance diff logs
   grep "perf_diff.query_comparison" /tmp/logs/backend_*.log
   
   # Verify speedup is positive
   # Expected: 5-50x faster for offline/unity queries
   ```

4. **If issues occur** (kill switch):
   ```bash
   READ_FROM_LAST_STATUS=false
   # Restart backend workflow
   ```

### Performance Diff Harness

Enable to compare legacy vs fast queries:

```bash
PERF_DIFF_ENABLED=true  # Run for 1 week, then disable
```

Check results:
```bash
grep "perf_diff" /tmp/logs/backend_*.log | grep speedup
```

Expected speedup: 5x-50x for status queries.

---

## Troubleshooting

### Performance Degradation

**Symptom**: p99 latency >300ms

**Diagnosis**:
```bash
# Check active connections
psql $DATABASE_URL -c "SELECT COUNT(*) FROM pg_stat_activity;"

# Check long-running queries
psql $DATABASE_URL -c "SELECT pid, now() - query_start as duration, query 
FROM pg_stat_activity 
WHERE state = 'active' AND query NOT LIKE '%pg_stat_activity%'
ORDER BY duration DESC;"

# Check table bloat
psql $DATABASE_URL -c "SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) 
FROM pg_tables 
WHERE tablename LIKE 'device_heartbeats%' 
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC LIMIT 10;"
```

**Fix**:
1. Check if VACUUM is running: `SELECT * FROM pg_stat_progress_vacuum;`
2. Manually VACUUM hot partitions:
   ```sql
   VACUUM ANALYZE device_heartbeats_YYYYMMDD;
   ```
3. If pool saturation, restart backend
4. Consider increasing pool size in `models.py` (current: 50 + 50 overflow)

### Partition Failures

**Symptom**: Partition creation failed

**Diagnosis**:
```bash
# Check disk space
df -h

# Check PostgreSQL logs
psql $DATABASE_URL -c "SELECT * FROM pg_stat_database WHERE datname = current_database();"

# Check for name conflicts
psql $DATABASE_URL -c "SELECT tablename FROM pg_tables WHERE tablename LIKE 'device_heartbeats_%';"
```

**Fix**:
```python
# Manual partition creation (idempotent)
from db_utils import create_heartbeat_partition
from datetime import date

create_heartbeat_partition(date(2025, 10, 20))
```

### Archive Issues

**Symptom**: Archive job stuck or failed

**Diagnosis**:
```sql
-- Check for held advisory lock
SELECT * FROM pg_locks WHERE locktype = 'advisory';

-- Check archive failures
SELECT partition_name, state, archived_at
FROM hb_partitions
WHERE state = 'archive_failed'
ORDER BY range_start DESC;
```

**Fix**:
```sql
-- Force unlock advisory lock (if stuck)
SELECT pg_advisory_unlock_all();

-- Reset failed archive
UPDATE hb_partitions
SET state = 'active'
WHERE partition_name = 'device_heartbeats_YYYYMMDD';

-- Re-run archive manually
-- (will be picked up by next nightly run)
```

### Data Consistency

**Symptom**: device_last_status out of sync with heartbeats

**Diagnosis**:
```sql
-- Find devices with stale last_status
SELECT 
    d.id,
    d.alias,
    dls.last_ts as last_status_ts,
    (SELECT MAX(ts) FROM device_heartbeats WHERE device_id = d.id) as latest_heartbeat_ts
FROM devices d
LEFT JOIN device_last_status dls ON d.id = dls.device_id
WHERE (SELECT MAX(ts) FROM device_heartbeats WHERE device_id = d.id) > dls.last_ts
LIMIT 10;
```

**Fix**:
```bash
# Run reconciliation job
cd server && python reconciliation_job.py

# If many discrepancies, re-backfill
cd server && python backfill_last_status.py --days 1
```

---

## Autovacuum Tuning

Current settings (PostgreSQL defaults):

```sql
-- Check current autovacuum settings
SHOW autovacuum_vacuum_scale_factor;  -- 0.2 (20% dead rows)
SHOW autovacuum_analyze_scale_factor; -- 0.1 (10% changed rows)
```

For high-write partitions, consider:

```sql
-- More aggressive autovacuum for active partitions
ALTER TABLE device_heartbeats_20251018 SET (
    autovacuum_vacuum_scale_factor = 0.05,
    autovacuum_analyze_scale_factor = 0.02
);
```

Monitor autovacuum activity:
```sql
SELECT * FROM pg_stat_progress_vacuum;
SELECT * FROM pg_stat_user_tables WHERE relname LIKE 'device_heartbeats%' ORDER BY last_autovacuum DESC;
```

---

## Connection Pool Validation

Current configuration (server/models.py):
- pool_size: 50
- max_overflow: 50
- **Total max**: 100 connections

PostgreSQL max_connections (Replit default): ~100

**Validation**:
```bash
# Check current connections
psql $DATABASE_URL -c "SELECT COUNT(*), state FROM pg_stat_activity GROUP BY state;"

# Check pool saturation (from metrics endpoint)
curl -s -H "x-admin: $ADMIN_KEY" https://your-domain.repl.co/metrics | grep db_pool
```

**Alerts** (add to monitoring):
- db_pool_in_use > 80: Warning
- db_pool_in_use > 95: Critical
- db_pool_waits_total increasing: Connection starvation

---

## Recovery Scenarios

### Complete Data Loss (Archive Recovery)

**Note**: Current implementation stubs actual object storage upload.

For production:
1. Configure S3/GCS credentials
2. Update `nightly_maintenance.py` to upload CSV files
3. Store checksum manifests

Recovery:
```bash
# Download archive from S3
aws s3 cp s3://nexmdm-archives/device_heartbeats_20250815.csv.gz .

# Verify checksum
sha256sum device_heartbeats_20250815.csv.gz
# Compare with hb_partitions.checksum_sha256

# Restore partition
psql $DATABASE_URL -c "CREATE TABLE device_heartbeats_20250815 PARTITION OF device_heartbeats..."
gunzip device_heartbeats_20250815.csv.gz
psql $DATABASE_URL -c "\COPY device_heartbeats_20250815 FROM device_heartbeats_20250815.csv CSV HEADER"
```

### Rollback Procedure

If fast-read migration causes issues:

1. **Disable feature flag**:
   ```bash
   READ_FROM_LAST_STATUS=false
   ```

2. **Restart backend** to clear connection pool

3. **Verify legacy queries work**:
   ```bash
   curl https://your-domain.repl.co/v1/devices
   ```

4. **Investigate** why fast reads failed:
   ```bash
   grep "fast_status" /tmp/logs/backend_*.log | grep -i error
   ```

---

## Monitoring Dashboard

### Key Metrics to Graph

1. **Heartbeat Latency**:
   - `http_request_latency_ms{route="/v1/heartbeat"}` (p50, p95, p99)

2. **Read Query Latency**:
   - `query_latency_fast_list_devices_ms` (p95, p99)
   - `query_latency_legacy_list_devices_ms` (compare)

3. **Partition Health**:
   - `partitions_created_total`
   - `partitions_archived_total`
   - `partition_create_failures_total`
   - `archive_failures_total`

4. **Database**:
   - `db_pool_in_use`
   - `db_pool_waits_total` (rate)

5. **Data Quality**:
   - `reconciliation_rows_updated_total` (should be low)
   - `heartbeats_ingested_total` (rate)

### Alert Thresholds

```yaml
- alert: HighHeartbeatLatency
  expr: histogram_quantile(0.99, http_request_latency_ms{route="/v1/heartbeat"}) > 300
  for: 5m

- alert: PartitionCreationFailed
  expr: increase(partition_create_failures_total[1h]) > 0
  for: 1m

- alert: ArchiveJobFailed
  expr: increase(archive_failures_total[24h]) > 0
  for: 1h

- alert: ReconciliationDrift
  expr: increase(reconciliation_rows_updated_total[1h]) > 1000
  for: 5m

- alert: ConnectionPoolSaturation
  expr: db_pool_in_use > 95
  for: 2m
```

---

## Capacity Planning

### Storage Growth

- **Per device**: ~10 heartbeats/day × 200 bytes = 2KB/day
- **500 devices**: 1MB/day, 90MB/90 days
- **2000 devices**: 4MB/day, 360MB/90 days

Partitions auto-archive and compress at 90 days.

### CPU & Memory

- **Heartbeat processing**: O(1) with bucketing
- **Read queries**: O(1) with device_last_status
- **VACUUM overhead**: ~5-10% CPU during nightly job

Expected resource usage (2000 devices):
- CPU: 30-50%
- Memory: 500MB-1GB
- DB connections: 30-60 active

---

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2025-10-18 | Initial partition system deployment | Agent |
| 2025-10-18 | Added device_last_status fast reads | Agent |
| 2025-10-18 | Implemented nightly maintenance job | Agent |
| 2025-10-18 | Added reconciliation job | Agent |

---

## Contacts & Resources

- **Replit Dashboard**: https://replit.com/@username/NexMDM
- **Metrics Endpoint**: `/metrics` (requires ADMIN_KEY)
- **Ops Endpoints**: `/ops/nightly`, `/ops/reconcile`
- **Database**: Replit PostgreSQL (Neon-backed)

For questions or issues, refer to this runbook first, then check logs.
