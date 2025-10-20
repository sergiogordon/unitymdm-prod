# CI Integration Guide for APK Management

This guide explains how to set up GitHub Actions (or other CI systems) to automatically register APK builds with the NexMDM backend.

## Overview

When you push code, your CI pipeline will:
1. Build the debug APK
2. Extract metadata (version, size, SHA256)
3. Upload the APK to storage (local or cloud)
4. Register the build with NexMDM backend
5. The APK appears automatically in the APK Management dashboard

## Prerequisites

### 1. Set up Secrets in GitHub

Add these secrets to your GitHub repository (`Settings` → `Secrets and variables` → `Actions`):

- `NEXMDM_BACKEND_URL`: Your backend URL (e.g., `https://your-repl.replit.dev`)
- `NEXMDM_ADMIN_KEY`: Your admin API key (from `.env` file's `ADMIN_KEY`)

### 2. Backend Configuration

Ensure your backend has the `ADMIN_KEY` environment variable set:

```bash
# In your .env file or Replit Secrets
ADMIN_KEY=your-secure-admin-key-here
```

## GitHub Actions Workflow

See `.github/workflows/build-and-register-apk.yml` for a complete example.

### Key Steps

1. **Build APK**:
   ```bash
   ./gradlew assembleDebug
   ```

2. **Extract Metadata**:
   - Version name and code from `build.gradle`
   - File size with `stat`
   - SHA256 checksum
   - Signer fingerprint

3. **Upload to Storage** (choose one):
   - **Local**: Copy APK to backend server via SCP
   - **S3**: Upload to AWS S3 bucket
   - **GCS**: Upload to Google Cloud Storage
   - **Backblaze B2**: Upload to Backblaze

4. **Register with Backend**:
   ```bash
   curl -X POST "$BACKEND_URL/admin/apk/register" \
     -H "X-Admin: $ADMIN_KEY" \
     -H "Content-Type: application/json" \
     -d '{ ... }'
   ```

## API Endpoint: POST /admin/apk/register

### Request Headers
- `X-Admin`: Your admin API key

### Request Body
```json
{
  "build_id": "gh_12345_67",
  "version_code": 42,
  "version_name": "1.3.0",
  "build_type": "debug",
  "file_size_bytes": 25123456,
  "sha256": "abc123...",
  "signer_fingerprint": "AA:BB:CC...",
  "storage_url": "./apk_storage/nexmdm-debug-1.3.0.apk",
  "ci_run_id": "12345",
  "git_sha": "abc123def456",
  "package_name": "com.nexmdm.agent"
}
```

### Response
```json
{
  "success": true,
  "action": "registered",
  "build_id": 123,
  "version_code": 42,
  "version_name": "1.3.0",
  "uploaded_at": "2025-10-20T12:34:56.789Z"
}
```

## Storage Options

### Option 1: Local File Storage (Current)

APKs are stored in `./apk_storage/` on the backend server.

**Pros**: Simple, no external dependencies
**Cons**: Limited scalability, no CDN

**Setup**: Copy APK to backend server via SCP:
```bash
scp app/build/outputs/apk/debug/app-debug.apk \
  backend:/path/to/apk_storage/
```

### Option 2: Cloud Storage (Recommended for Production)

Use AWS S3, Google Cloud Storage, or Backblaze B2.

**Pros**: Scalable, CDN support, versioning
**Cons**: Requires cloud account, costs

**Example with S3**:
```bash
aws s3 cp app-debug.apk \
  s3://your-bucket/apk/debug/nexmdm-1.3.0.apk
```

Update the `storage_url` field to point to the cloud URL.

## Frontend Dashboard

Once registered, builds appear automatically in the APK Management page at `/apk-management`:

- Lists all debug builds
- Shows version, size, upload time
- Download button for each build
- Delete button to remove builds

## Testing

1. **Manual Test**: Call the register endpoint with `curl`:
   ```bash
   curl -X POST "http://localhost:8000/admin/apk/register" \
     -H "X-Admin: your-admin-key" \
     -H "Content-Type: application/json" \
     -d '{
       "build_id": "test_123",
       "version_code": 1,
       "version_name": "1.0.0-test",
       "build_type": "debug",
       "file_size_bytes": 1000000,
       "package_name": "com.nexmdm.agent"
     }'
   ```

2. **Verify in Dashboard**:
   - Open `/apk-management`
   - You should see the test build listed
   - Download and delete buttons should work

3. **Check Logs**:
   - Backend logs show `apk.register` events
   - Metrics track `apk_builds_total{build_type="debug"}`

## Troubleshooting

### Build not appearing in dashboard

1. Check backend logs for errors
2. Verify `ADMIN_KEY` is correct
3. Ensure `build_type=debug` parameter is set
4. Check backend `/admin/apk/builds?build_type=debug` API directly

### Download fails

1. Verify APK file exists at `storage_url`
2. Check file permissions
3. Ensure backend can read the file

### CI workflow fails

1. Check GitHub Actions logs
2. Verify secrets are set correctly
3. Ensure backend is accessible from GitHub runners
4. Test API endpoint manually with `curl`

## Security

- **Admin Key**: Keep `ADMIN_KEY` secret, rotate periodically
- **HTTPS**: Always use HTTPS in production
- **Scoped Keys**: Consider implementing scoped admin keys (future)
- **IP Allowlist**: Restrict API access to CI IP ranges (optional)

## Metrics and Observability

The backend tracks:
- `apk_builds_total{build_type, action}`: Total builds registered
- `apk_download_total{build_type, source}`: Total downloads
- `apk_delete_total{build_type}`: Total deletions

Logs include:
- `apk.register`: Build registration events
- `apk.download`: Download events with source
- `apk.delete`: Deletion events
