# GitHub Actions Auto-Upload Setup

This guide explains how to configure GitHub Actions to automatically upload built APKs to your NexMDM backend.

## 🎯 What This Does

When you push Android code changes to the `main` branch:
1. GitHub Actions builds the APK automatically
2. Extracts APK metadata (package name, version code, version name)
3. **Uploads the APK to your NexMDM backend automatically**
4. APK appears in your dashboard, ready to deploy to devices!

**No more manual downloading, extracting, or uploading!** 🚀

---

## 📋 Prerequisites

- Your NexMDM backend is running on Replit
- You have access to your ADMIN_KEY secret
- Your repository is on GitHub

---

## ⚙️ Setup Instructions

### Step 1: Get Your Backend URL

Your NexMDM backend URL is:
```
https://628b02e5-4895-4870-9281-e541294fbe81-00-lk7z8wij3ttr.picard.replit.dev
```

(This is stored in the `REPLIT_DEV_DOMAIN` environment variable)

### Step 2: Get Your Admin Key

Your ADMIN_KEY is already stored as a Replit secret. You can view it in:
- Replit → Tools → Secrets → `ADMIN_KEY`

**Important:** Copy this value - you'll need it for GitHub.

### Step 3: Add GitHub Secrets

1. Go to your GitHub repository
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add these two secrets:

#### Secret 1: NEXMDM_API_URL
- **Name:** `NEXMDM_API_URL`
- **Value:** `https://628b02e5-4895-4870-9281-e541294fbe81-00-lk7z8wij3ttr.picard.replit.dev`

#### Secret 2: ADMIN_KEY
- **Name:** `ADMIN_KEY`
- **Value:** (paste your ADMIN_KEY from Replit Secrets)

---

## ✅ Verify Setup

Once configured, the workflow will:

1. **Automatically trigger** when you push to `main` branch with Android changes
2. **Build the APK** using Gradle
3. **Extract metadata** using Android build tools
4. **Upload to backend** using the `/v1/apk/upload` API endpoint
5. **Show results** in GitHub Actions logs

### Check Upload Status

After pushing code:
1. Go to **Actions** tab in GitHub
2. Click the latest workflow run
3. Expand **"Upload APK to NexMDM Backend"** step
4. You should see: `✅ APK uploaded successfully!`

---

## 🔍 Troubleshooting

### Upload fails with 401 Unauthorized
- Check that `ADMIN_KEY` secret matches your Replit secret exactly
- Verify the secret name is `ADMIN_KEY` (case-sensitive)

### Upload fails with connection error
- Verify `NEXMDM_API_URL` is correct
- Make sure your Replit backend is running
- Check that the URL includes `https://` prefix

### APK metadata extraction fails
- This usually means the APK build failed
- Check the **"Build Debug APK"** step for errors
- Verify Android build tools are installed in the workflow

### Upload is skipped or fails silently
- The upload only runs on the `main` branch (check you pushed to `main`)
- If secrets are not configured, the upload will fail but the workflow continues
- Verify both `NEXMDM_API_URL` and `ADMIN_KEY` secrets are configured in GitHub
- Check the workflow logs to see the specific error message

---

## 🔐 Security Notes

- **ADMIN_KEY** is used for authentication (same key used for enrollment)
- API key is sent as a form field for reliable multipart upload handling
- Uploaded APKs are attributed to `github-actions` user in the backend
- Secrets are encrypted by GitHub and never exposed in logs

---

## 🚀 Usage

After setup, just push your code:

```bash
# Make changes to Android app
cd android
# ... edit code ...

# Commit and push
git add .
git commit -m "Update Android app"
git push origin main
```

GitHub Actions will:
1. ✅ Build APK
2. ✅ Extract metadata  
3. ✅ Upload to backend
4. ✅ Make it available in dashboard

Then you can deploy it to devices from your NexMDM dashboard! 🎉

---

## 📊 Backend API

The automation uses this endpoint:

```bash
POST /v1/apk/upload
Body (multipart/form-data):
  file: {apk_file}
  package_name: com.nexmdm
  version_name: 1.0.0
  version_code: 1
  notes: Automated build from commit {sha}
  api_key: {ADMIN_KEY}
```

The backend supports both:
- **Session authentication** (for dashboard uploads)
- **API key authentication** (for GitHub Actions - sent as form field)
