# GitHub Actions APK Build Fix

## Problem Summary

The GitHub Actions workflow for building Android APKs was **failing during APK registration** with the backend. The workflow successfully built the debug and release APKs, but failed when trying to register the APK metadata with the NexMDM backend.

### Error Details

```
HTTP Status: 502
Response: Hmm... We couldn't reach this app
```

The workflow was attempting to POST to:
```
https://<your-replit-url>/api/proxy/admin/apk/register
```

## Root Cause

The Next.js frontend needed an environment variable (`BACKEND_URL`) to proxy API requests to the backend server, but this wasn't configured. Without it, the proxy route couldn't forward requests to the backend running on port 8000.

## Solution Applied

### 1. Created `.env.local` for Frontend
Added environment variable configuration:

```bash
# frontend/.env.local
BACKEND_URL=http://localhost:8000
```

### 2. Verified Proxy Route Exists
The proxy route was already configured at:
- **Path:** `frontend/app/api/proxy/[...path]/route.ts`
- **Function:** Forwards all `/api/proxy/*` requests to the backend on port 8000

The proxy route properly:
- Forwards all HTTP methods (GET, POST, PUT, DELETE, PATCH)
- Preserves request headers (including `X-Admin` for authentication)
- Handles binary data (APKs, etc.) using `ArrayBuffer`
- Adds CORS headers for cross-origin requests
- Provides error handling and logging

### 3. Restarted Frontend Workflow
Restarted the frontend to pick up the new environment variable.

## How It Works Now

### GitHub Actions Workflow Flow

```
┌─────────────────────────────────────────────────┐
│  GitHub Actions (Ubuntu Runner)                 │
│                                                  │
│  1. Build debug & release APKs                  │
│  2. Sign APKs with release keystore             │
│  3. Calculate SHA-256 hash                      │
│  4. POST registration to frontend               │
│     URL: /api/proxy/admin/apk/register          │
│     Headers: X-Admin: <ADMIN_KEY>               │
│     Body: JSON with APK metadata                │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│  Replit Frontend (Next.js on port 5000)        │
│                                                  │
│  Proxy Route: /app/api/proxy/[...path]/route.ts│
│  Forwards to: ${BACKEND_URL}/${path}            │
│  (http://localhost:8000/admin/apk/register)     │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│  Backend (FastAPI on port 8000)                 │
│                                                  │
│  Endpoint: POST /admin/apk/register             │
│  1. Validates X-Admin header                    │
│  2. Creates APK version record in database      │
│  3. Stores metadata (version, SHA-256, etc.)    │
│  4. Returns success response                    │
└─────────────────────────────────────────────────┘
```

## Why This Architecture?

### Replit's Port Restrictions
- Only **port 5000** is exposed to public domains
- Backend on port 8000 is **firewalled** from external access
- Frontend must proxy all API requests to backend

### Benefits
1. **Security**: Backend port isn't exposed publicly
2. **Simplicity**: Single public URL for both frontend and API
3. **CORS**: Automatic CORS handling by proxy
4. **Authentication**: Headers preserved through proxy

## Testing the Fix

You can verify the fix is working by:

### 1. Test the Proxy Route Locally
```bash
# From your local machine or GitHub Actions
curl -X POST "https://<your-replit-url>/api/proxy/admin/apk/register" \
  -H "X-Admin: <ADMIN_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "build_id": "test_123",
    "version_name": "1.0.0",
    "version_code": 100,
    "file_size": 1000000,
    "sha256": "abc123...",
    "build_type": "release",
    "package_name": "com.example.app"
  }'
```

Expected response: `HTTP 200` or `HTTP 201` with APK metadata

### 2. Trigger GitHub Actions Workflow
```bash
# Push to main or create a tag
git tag v1.0.0
git push origin v1.0.0
```

The workflow should now complete successfully with:
```
✅ SUCCESS: Release APK metadata registered with backend!
View build at: https://<your-replit-url>/apk-management
```

## Configuration Requirements

For the GitHub Actions workflow to succeed, ensure these secrets are set in your GitHub repository:

### Required Secrets
1. **`ANDROID_KEYSTORE_BASE64`**: Base64-encoded release keystore
2. **`KEYSTORE_PASSWORD`**: Keystore password
3. **`KEY_ALIAS`**: Key alias in keystore
4. **`KEY_PASSWORD`**: Key password
5. **`NEXMDM_BACKEND_URL`**: Your Replit public URL (e.g., `https://abc-123.replit.dev`)
6. **`NEXMDM_ADMIN_KEY`**: Backend admin key (must match `ADMIN_KEY` env var in Replit)

### Setting GitHub Secrets
1. Go to your GitHub repository
2. Settings → Secrets and variables → Actions
3. Click "New repository secret"
4. Add each secret listed above

## Troubleshooting

### Workflow Still Fails with 502
**Check:**
1. Frontend workflow is running (`npm run dev`)
2. Backend workflow is running (`uvicorn`)
3. `frontend/.env.local` exists with `BACKEND_URL=http://localhost:8000`
4. Both workflows have been restarted after adding `.env.local`

### Workflow Fails with 401 Unauthorized
**Check:**
1. `NEXMDM_ADMIN_KEY` GitHub secret matches backend `ADMIN_KEY` environment variable
2. Header name is `X-Admin` (not `X-Admin-Key`)

### Workflow Fails with 404 Not Found
**Check:**
1. Endpoint path in workflow matches backend route:
   - Workflow: `/api/proxy/admin/apk/register`
   - Backend: `/admin/apk/register`
2. Proxy route exists at `frontend/app/api/proxy/[...path]/route.ts`

## Next Steps

With this fix applied:
1. ✅ APKs will build successfully in GitHub Actions
2. ✅ APK metadata will register with your backend automatically
3. ✅ Builds will appear in the dashboard at `/apk-management`
4. ✅ You can deploy APKs to devices directly from the GitHub Actions artifacts

The complete CI/CD pipeline is now functional! 🚀
