# Database Migration Guide: Development to Production

This guide helps you migrate your device data from the development database to the production database WITHOUT requiring device re-enrollment.

## Files Included

- `schema_export.sql` - Complete database schema (132KB)
- `data_export.sql` - All data including devices, users, and settings (1.3MB)

## Data Summary

| Table | Records | Notes |
|-------|---------|-------|
| devices | 93 | All enrolled devices with credentials |
| device_last_status | 93 | Fast-lookup status cache |
| users | 2 | Admin users |
| apk_versions | 129 | APK build records |
| alert_states | 178 | Alert tracking |
| bloatware_packages | 72 | Bloatware list |
| remote_exec | 105 | Command history |
| bulk_commands | 17 | Bulk command records |
| discord_settings | 1 | Discord config |
| monitoring_defaults | 1 | Monitoring config |
| wifi_settings | 1 | WiFi config |

**Excluded (not needed for migration):**
- `device_heartbeats_*` - Historical heartbeat partitions (not critical)
- `alembic_version` - Will be set by migrations
- `hb_partitions` - Partition metadata

## Migration Steps

### Step 1: Deploy to Production

First, deploy your app to production in Replit. This will automatically create a production database.

### Step 2: Get Production Database URL

After deployment, go to **Secrets** in your Replit project and find the production `DATABASE_URL`. It will be different from the development one.

### Step 3: Run Alembic Migrations on Production

Connect to your production database and run migrations:

```bash
# Set the production DATABASE_URL temporarily
export DATABASE_URL="your-production-database-url-here"

# Run Alembic migrations to create schema
cd server && alembic upgrade head
```

### Step 4: Import Data

After migrations complete, import the data:

```bash
# Import data into production
psql "your-production-database-url-here" -f db_migration/data_export.sql
```

### Step 5: Verify

Check that devices are present in production:

```bash
psql "your-production-database-url-here" -c "SELECT COUNT(*) FROM devices;"
```

Should return: 93

## Important Notes

1. **Device credentials are preserved** - The `devices` table contains hashed tokens that devices use to authenticate. These are migrated as-is.

2. **No re-enrollment needed** - Devices will continue to authenticate normally because their credentials exist in the production database.

3. **FCM tokens preserved** - Push notification tokens are also migrated.

4. **Do this during low-traffic** - Ideally perform migration when fewer devices are actively sending heartbeats.

## Troubleshooting

If devices can't authenticate after migration:
1. Verify the data import completed successfully
2. Check that `devices` table has all 93 records
3. Ensure production DATABASE_URL is correctly configured in deployment secrets

## Alternative: Using Replit Database Panel

You can also access the production database through Replit's Database panel after deployment:
1. Go to your deployed app
2. Open the Database tab
3. Use the SQL console to run the import commands
