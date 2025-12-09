# Production Environment Setup

## Required Environment Variables

To ensure all routes use the production backend, set the following environment variables:

### Backend (FastAPI Server)

**Required:**
- `BACKEND_URL=https://unitymdm.replit.app/`
  - This ensures APK download URLs generated in FCM messages point to production
  - The trailing slash will be automatically normalized

**Optional (for automatic detection):**
- `REPLIT_DEPLOYMENT=1` (if using Replit deployment detection)
- `REPLIT_DOMAINS=unitymdm.replit.app` (if using Replit domain detection)

### Frontend (Next.js)

**Required:**
- `BACKEND_URL=https://unitymdm.replit.app/`
  - This ensures all frontend API routes proxy to production backend
  - The trailing slash will be automatically normalized

**Optional:**
- `NEXT_PUBLIC_BACKEND_URL=https://unitymdm.replit.app/` (alternative to BACKEND_URL)

## Migration from Dev Proxy Setup

If you previously used `PROD_BACKEND_URL` for dev-to-prod proxying:

1. **Remove `PROD_BACKEND_URL`** from your environment variables
2. **Set `BACKEND_URL=https://unitymdm.replit.app/`** in both frontend and backend
3. **Restart both services** to load the new configuration

The simplified backend URL logic no longer supports `PROD_BACKEND_URL` - all routes now use `BACKEND_URL` consistently.

## Verification

After setting environment variables and restarting:

### Backend Verification
Check backend startup logs for:
```
[CONFIG] Using manual BACKEND_URL: https://unitymdm.replit.app
```

### Frontend Verification
Check frontend logs for API requests:
```
[BackendURL] Using production backend: https://unitymdm.replit.app (route: v1/devices)
```

### Test APK Deployment
1. Deploy a Unity APK to a device
2. Check FCM message payload - `download_url` should be: `https://unitymdm.replit.app/v1/apk/download/{id}`
3. Verify device can successfully download the APK

## Troubleshooting

**Still seeing localhost URLs:**
- Verify `BACKEND_URL` is set correctly (no typos)
- Restart both backend and frontend services
- Check logs to confirm which URL is being used

**403 Forbidden errors:**
- Check that installation records have correct `device_id`
- Verify device tokens are resolving to correct devices
- Check backend logs for device_id mismatch details

**Download failures:**
- Verify `BACKEND_URL` is set to HTTPS (not HTTP)
- Check that the endpoint is accessible: `curl -I https://unitymdm.replit.app/v1/apk/download/139`
- Ensure Android devices can reach the production domain

