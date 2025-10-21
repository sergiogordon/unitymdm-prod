# Replit App Storage Setup for APK Management

## ✅ Code Migration Complete

All code has been migrated to use **Replit Object Storage SDK** - a native Python SDK that handles authentication automatically through the Replit sidecar.

## 📦 What Changed

### Updated Files
1. **server/object_storage.py** - Rewritten to use native `replit.object_storage.Client`
2. **server/main.py** - All upload/download/delete endpoints use the new storage service
3. **Dependencies** - Removed direct google-cloud-storage usage; now using replit-object-storage

### Key Benefits
- ✅ **No authentication errors** - Replit sidecar handles all auth automatically
- ✅ **Persistent storage** - Files survive server restarts and deployments
- ✅ **Scalable** - No disk space limits, backed by GCS
- ✅ **Production-ready** - High availability with automatic backups
- ✅ **Simplified setup** - No manual bucket or environment variable configuration needed

## 🔧 Required Setup Steps

### Step 1: Enable App Storage

1. Open the **App Storage** tool in your Replit workspace:
   - Click "Tools" in the left sidebar → "Storage"
   - OR search for "Storage" in the workspace tools

2. If not already enabled, click **"Enable App Storage"**
   - This provisions a default bucket and configures the sidecar

3. Restart your deployment/repl to ensure the sidecar picks up the new credentials

### That's It!

No bucket names, no environment variables needed. The `replit.object_storage.Client()` automatically uses your default bucket.

## 🧪 Testing the Integration

Once setup is complete, you can test:

```bash
# 1. Register a test APK build
curl -X POST http://localhost:8000/admin/apk/register \
  -H "X-Admin: YOUR_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "build_id": "test_123",
    "version_code": 999,
    "version_name": "1.0.999-test",
    "build_type": "debug",
    "package_name": "com.nexmdm.agent"
  }'

# 2. Upload an APK file
curl -X POST http://localhost:8000/admin/apk/upload \
  -H "X-Admin: YOUR_ADMIN_KEY" \
  -F "file=@path/to/test.apk" \
  -F "build_id=test_123" \
  -F "version_code=999" \
  -F "version_name=1.0.999-test" \
  -F "build_type=debug" \
  -F "package_name=com.nexmdm.agent"

# 3. Download and verify
curl http://localhost:8000/admin/apk/download/{build_id} \
  -H "X-Admin: YOUR_ADMIN_KEY" \
  -o test.apk
```

## 📊 Architecture Details

### Upload Flow
```
GitHub Actions → /admin/apk/upload (FastAPI)
                        ↓
                object_storage.upload_file()
                        ↓
                replit.object_storage.Client.upload_from_bytes()
                        ↓
                Replit Storage Sidecar (127.0.0.1:1106)
                        ↓
                Google Cloud Storage
                        ↓
                Store path as storage://apk/debug/{uuid}_{filename} in PostgreSQL
```

### Download Flow
```
User/Device Request → Download endpoint → object_storage.download_file()
                                                ↓
                                        replit.object_storage.Client.download_as_bytes()
                                                ↓
                                        Fetch from GCS → Stream to client
```

### Storage Paths
- Files stored with keys: `apk/debug/{uuid}_{filename}.apk`
- Database stores paths as: `storage://apk/debug/{uuid}_{filename}.apk`
- Maximum file size: 60 MB
- Only `.apk` files accepted

## 🔒 Security & Access

- **Authentication**: All endpoints require admin key or device tokens
- **Credentials**: Replit sidecar (127.0.0.1:1106) provides credentials automatically
- **No manual token management**: The SDK handles everything
- **File validation**: Size limits and extension checks enforced

## 📝 Logging

All storage operations are logged with structured events:
- `storage.upload.start` / `storage.upload.success` / `storage.upload.error`
- `storage.download.start` / `storage.download.success` / `storage.download.error`
- `storage.delete.success` / `storage.delete.error`

Each log includes:
- Storage key
- File size
- Error details (if applicable)

## 🚀 Next Steps

After enabling storage:
1. Test APK upload via GitHub Actions workflow
2. Verify downloads from the APK Management dashboard
3. Monitor storage usage in the Storage tool
4. Check backend logs for storage operation events

## 💡 Troubleshooting

### Error: "Failed to initialize storage client"
- Make sure App Storage is enabled in Tools → Storage
- Restart the deployment/repl after enabling storage
- Verify you're running on Replit (not locally)

### Error: "Storage service error: UnauthorizedError"
- Disable and re-enable App Storage in the Tools panel
- This forces re-provisioning of service account credentials
- Restart the deployment after re-enabling

### Error: "File too large: X MB. Maximum allowed: 60MB"
- APK files are limited to 60MB
- Check your APK size and optimize if needed

### Files Not Showing Up
- Check backend logs for `storage.upload.error` events
- Verify the App Storage tool shows the bucket is active
- Look for `storage://apk/debug/` paths in your database
