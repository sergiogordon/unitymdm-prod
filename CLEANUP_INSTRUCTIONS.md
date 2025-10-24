# Test Device Cleanup Script

## Overview
This script safely removes test devices created during the bug bash using the bulk delete API. It authenticates with JWT, fetches all devices, displays them for review, and requests confirmation before deletion.

## Usage

### Run the script:
```bash
python3 cleanup_test_devices.py
```

### What it does:
1. **Authenticates** with the backend using admin credentials
2. **Fetches all devices** from the API (handles pagination automatically)
3. **Displays summary** with:
   - Total device count
   - Online/offline breakdown
   - Sample device aliases for verification
4. **Requests confirmation** - Type "DELETE ALL" to proceed
5. **Performs bulk deletion** via `/v1/devices/bulk-delete` API
6. **Reports progress** and confirms deletion

## Current System State
- **Total Devices**: 202 (1 online, 201 offline)
- **Authentication**: JWT-based admin login
- **API Endpoint**: `/v1/devices/bulk-delete`
- **Safety Features**: Confirmation prompt, batch size reporting

## API Details
The script uses:
- `POST /api/auth/login` - Authenticates and gets JWT token
- `GET /v1/devices?page=X&limit=100` - Fetches paginated device list
- `POST /v1/devices/bulk-delete` - Deletes devices by ID list

## Safety Notes
- Requires explicit confirmation ("DELETE ALL")
- Shows device count before deletion
- Uses the same bulk delete API as the admin dashboard
- Respects rate limiting and queue constraints
- Database-level cascading deletion ensures complete cleanup

## Expected Outcome
After running successfully:
- All 202 test devices removed from database
- Device tokens revoked
- Heartbeat history cleaned up (90-day retention still applies)
- KPI tiles show accurate counts
- Dashboard shows clean slate

## Troubleshooting
- **Auth failure**: Verify admin credentials in script
- **Connection error**: Ensure backend is running on port 8000
- **Timeout**: Large deletions may take time, be patient
- **Partial deletion**: Re-run the script to clean remaining devices
