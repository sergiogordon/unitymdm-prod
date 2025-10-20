# GitHub Actions Setup Guide

This guide explains how to configure GitHub Actions to automatically build and register your Android APKs with the NexMDM backend running on Replit.

## Prerequisites

1. **Android Project**: Your Android app code must be in the same repository as this workflow file
2. **Replit Backend**: Your NexMDM backend must be running and accessible
3. **GitHub Repository**: Your code must be in a GitHub repository

## Step 1: Get Your Replit Backend URL

Your Replit app URL is available in the environment as `REPLIT_DOMAINS`. For this Repl, the URL is:

```
https://83b071bb-c5cb-4eda-b79c-d276873904c2-00-2ha4ytvejclnm.worf.replit.dev
```

**Important**: Make sure your backend workflow is running before setting up GitHub Actions.

## Step 2: Configure GitHub Secrets

You need to add two secrets to your GitHub repository:

### Navigate to Secrets

1. Go to your GitHub repository
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**

### Add Required Secrets

#### Secret 1: NEXMDM_BACKEND_URL

- **Name**: `NEXMDM_BACKEND_URL`
- **Value**: `https://83b071bb-c5cb-4eda-b79c-d276873904c2-00-2ha4ytvejclnm.worf.replit.dev`

This is your Replit app's public URL where the backend is running.

#### Secret 2: NEXMDM_ADMIN_KEY

- **Name**: `NEXMDM_ADMIN_KEY`
- **Value**: Your admin API key from the `.env` file

To find your admin key:
1. Check your Replit Secrets (🔒 icon in left sidebar)
2. Look for `ADMIN_KEY`
3. Copy the value (it should be a long random string)

## Step 3: Add the Workflow File

The workflow file is already in your repository at:
```
.github/workflows/build-and-register-apk.yml
```

This workflow will:
1. Trigger on pushes to `main` or `develop` branches
2. Build your Android debug APK
3. Extract metadata (version, size, SHA256 hash)
4. Register the build with your Replit backend
5. Upload the APK as a GitHub artifact

## Step 4: Verify Setup

### Test the Workflow

1. Make a commit to your `main` or `develop` branch:
   ```bash
   git add .
   git commit -m "Test APK build workflow"
   git push origin main
   ```

2. Go to **Actions** tab in your GitHub repository

3. You should see the workflow running

4. Check the APK Management page in your NexMDM dashboard - the new build should appear automatically

### Troubleshooting

If the workflow fails, check:

1. **Secrets are set correctly**:
   - `NEXMDM_BACKEND_URL` should start with `https://`
   - `NEXMDM_ADMIN_KEY` should match your backend's `ADMIN_KEY`

2. **Backend is running**:
   - Visit your Replit URL in a browser
   - Backend should be accessible and responding

3. **Workflow logs**:
   - Click on the failed workflow run
   - Check the "Register build with NexMDM backend" step
   - Look for error messages in the output

## Step 5: Manual Trigger (Optional)

You can also trigger the workflow manually:

1. Go to **Actions** tab
2. Click **Build and Register Debug APK** workflow
3. Click **Run workflow**
4. Select the branch
5. Click **Run workflow** button

## What Happens After Registration

Once a build is registered:

1. **APK Management Dashboard**: The build appears in `/apk-management` page
2. **Metadata Display**: Shows version, size, upload time (in CST), Git SHA
3. **GitHub Artifact**: APK is available in GitHub Actions artifacts for 30 days
4. **Download Link**: Currently points to GitHub Actions run page

## Storage Notes

The current setup uses GitHub Artifacts for APK storage (free for 30 days). For production:

- Consider uploading APKs to S3, Google Cloud Storage, or Backblaze B2
- Update the `storage_url` in the workflow to point to the cloud storage URL
- Implement actual file upload in the workflow before registering

## Security

- **Never commit secrets** to your repository
- Always use GitHub Secrets for sensitive values
- Rotate your `ADMIN_KEY` periodically
- Review workflow runs for any exposed credentials

## Next Steps

Once builds are appearing in your dashboard, you can:
- View build history and metadata
- Track which Git commits produced which builds
- Monitor APK sizes and versions
- Use this for OTA updates to your device fleet
