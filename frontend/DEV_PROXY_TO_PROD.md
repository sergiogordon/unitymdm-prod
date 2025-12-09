# Dev Replit Proxy to Prod - Configuration Guide

## Overview

This feature allows the dev Replit frontend to selectively proxy device requests to the production backend. This enables devices configured with the dev URL to reach the prod backend without requiring APK updates, while keeping admin/web UI routes pointing to the local dev database.

## How It Works

When `PROD_BACKEND_URL` environment variable is set in the dev Replit:
- **Device routes** (`/v1/*`) → Proxy to production backend
- **Admin routes** (`/admin/*`) → Always use local backend (dev database)
- **Auth routes** (`/api/auth/*`) → Always use local backend (dev database)

This allows devices to connect to prod while you can still manage devices using the dev database in the web UI.

**Priority Order:**
1. `PROD_BACKEND_URL` (if set, proxies to prod)
2. `BACKEND_URL` (normal backend URL)
3. `NEXT_PUBLIC_BACKEND_URL` (public backend URL)
4. `http://localhost:8000` (fallback)

## Setup (Enable Proxy to Prod)

1. **In your dev Replit**, go to **Secrets** (environment variables)
2. Add a new secret:
   - **Name**: `PROD_BACKEND_URL`
   - **Value**: `https://unitymdm.replit.app` (your prod backend URL)
3. **Restart the dev frontend** (or restart the dev Replit)
4. Check logs - you should see: `[BackendURL] PROD_BACKEND_URL set - proxying to production: https://unitymdm.replit.app`

## Verification

After setting `PROD_BACKEND_URL`:

**Device Operations (proxied to prod):**
- Devices with dev URL can send heartbeats to prod backend
- Devices can download APKs from prod backend
- Devices can receive FCM commands from prod backend
- All device-facing operations work

**Admin/Web UI (uses local dev database):**
- Device table loads from dev database
- APK management uses dev database
- All admin operations use local backend
- You can deploy APKs to devices from dev UI

## Revert (Disable Proxy to Prod)

When all devices are migrated to prod URL and you want to revert:

1. **In your dev Replit**, go to **Secrets**
2. **Delete** the `PROD_BACKEND_URL` environment variable
3. **Restart the dev frontend** (or restart the dev Replit)
4. The proxy will automatically revert to using the local backend

**No code changes needed** - simply removing the environment variable reverts the behavior.

## Files Modified

- `frontend/lib/backend-url.ts` - Shared utility for backend URL resolution
- `frontend/app/api/proxy/[...path]/route.ts` - Main proxy route
- All `frontend/app/v1/**/route.ts` - Device API routes (26 files)
- `frontend/app/api/apk/upload/route.ts` - APK upload route

## Logging

When `PROD_BACKEND_URL` is set, you'll see different logs based on route type:

**Device routes (proxied to prod):**
```
[BackendURL] PROD_BACKEND_URL set - proxying device route to production: https://unitymdm.replit.app (route: v1/heartbeat)
[Proxy] POST v1/heartbeat -> https://unitymdm.replit.app/v1/heartbeat
```

**Admin routes (using local backend):**
```
[BackendURL] Using local backend for admin route: http://localhost:8000 (route: admin/devices)
[Proxy] GET admin/devices -> http://localhost:8000/admin/devices
```

When `PROD_BACKEND_URL` is not set (normal mode):
```
[BackendURL] Using backend URL: http://localhost:8000
[Proxy] POST v1/heartbeat -> http://localhost:8000/v1/heartbeat
```

## Troubleshooting

**Devices still can't connect:**
- Verify `PROD_BACKEND_URL` is set correctly in dev Replit secrets
- Check dev frontend logs for proxy messages
- Verify prod backend is accessible from dev Replit
- Check that dev frontend was restarted after setting the env var

**Want to test before enabling:**
- Set `PROD_BACKEND_URL` temporarily
- Test with one device
- If it works, keep it enabled
- If not, remove the env var to revert

## Next Steps (After Devices Are Working)

Once devices are connecting via the proxy:
1. Consider implementing FCM-based server URL updates (future enhancement)
2. Deploy new APKs with prod URL to devices
3. Once all devices are on prod URL, remove `PROD_BACKEND_URL` to revert

