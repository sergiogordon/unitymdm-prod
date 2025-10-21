# Replit App Storage Setup for APK Management

## ✅ Code Migration Complete

All code has been migrated from local file storage to **Replit App Storage** (Google Cloud Storage backed).

## 📦 What Changed

### Updated Files
1. **server/object_storage.py** - New Python service for App Storage integration
2. **server/apk_manager.py** - Upload logic now uses cloud storage
3. **server/main.py** - All download/delete endpoints now use cloud storage

### Key Benefits
- ✅ **Persistent storage** - Files survive server restarts and deployments
- ✅ **Scalable** - No disk space limits, backed by GCS
- ✅ **Production-ready** - High availability with automatic backups
- ✅ **No data loss** - Files are stored in the cloud, not on ephemeral servers

## 🔧 Required Setup Steps

### Step 1: Create App Storage Bucket

1. Open the **App Storage** tool in your Replit workspace:
   - Click "Tools" in the left sidebar → "App Storage"
   - OR search for "App Storage" in the command palette

2. Click **"Create new bucket"**

3. Name your bucket: `nexmdm-apks` (or any name you prefer)

4. Click **"Create bucket"**

### Step 2: Set Environment Variable

1. Open the **Secrets** tool in your Replit workspace

2. Add a new secret:
   - **Key**: `PRIVATE_OBJECT_DIR`
   - **Value**: `/nexmdm-apks/apks`
   
   Format: `/{bucket_name}/{folder_path}`

3. Click **"Add new secret"** / Save

### Step 3: Restart Backend

After setting the environment variable, restart the backend workflow to apply changes.

## 🧪 Testing the Integration

Once setup is complete, you can test:

```bash
# 1. Register a test APK build
curl -X POST http://localhost:8000/admin/apk/register \
  -H "X-Admin: ldWh9geFGp2QbdRQQWvzGzwI56hb2FD4GdC48CKjT1Y=" \
  -H "Content-Type: application/json" \
  -d '{
    "build_id": "test_123",
    "version_code": 999,
    "version_name": "1.0.999-test",
    "build_type": "debug",
    "package_name": "com.nexmdm"
  }'

# 2. Upload an APK file
# (Use the upload endpoint with a real APK file)

# 3. Download and verify
curl http://localhost:8000/admin/apk/download/{build_id} \
  -H "X-Admin: ldWh9geFGp2QbdRQQWvzGzwI56hb2FD4GdC48CKjT1Y=" \
  -o test.apk
```

## 📊 Architecture Details

### Upload Flow
```
GitHub Actions → /api/apk/upload (Next.js proxy) → /admin/apk/upload (FastAPI)
                                                    ↓
                                            object_storage.upload_file()
                                                    ↓
                                            Google Cloud Storage (via Replit sidecar)
                                                    ↓
                                            Store path in PostgreSQL
```

### Download Flow
```
User/Device Request → Download endpoint → object_storage.download_file()
                                                    ↓
                                            Fetch from GCS → Stream to client
```

### Storage Paths
- Files stored as: `/nexmdm-apks/apks/{uuid}_{package}_{version_code}.apk`
- Database stores full object path for later retrieval
- No local filesystem dependencies

## 🔒 Security & Access

- **Authentication**: All endpoints require admin key or device tokens
- **Credentials**: Replit sidecar (127.0.0.1:1106) provides GCS credentials automatically
- **No manual token management**: The Python SDK handles auth via Replit's infrastructure

## 🚀 Next Steps

After completing the setup:
1. Test APK upload via GitHub Actions workflow
2. Verify downloads from the APK Management dashboard
3. Monitor storage usage in the App Storage tool
4. Update any documentation or onboarding materials

## 💡 Troubleshooting

### Error: "PRIVATE_OBJECT_DIR not set"
- Make sure you've added the secret in the Secrets tool
- Restart the backend workflow after adding secrets
- Verify the format: `/bucket_name/path`

### Error: "Failed to get Replit storage credentials"
- This usually means the Replit sidecar isn't available
- Make sure you're running on Replit (not locally)
- Check that port 1106 is accessible

### Files Not Showing Up
- Verify the bucket name matches the environment variable
- Check the App Storage tool to see if files are being created
- Look at backend logs for upload errors
