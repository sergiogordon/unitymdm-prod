# GitHub Actions Setup Guide

This guide explains how to configure GitHub Actions to automatically build and register your Android APKs with the NexMDM backend running on Replit.

## Project Structure

Your Android app is located in the `/android` folder of this repository. The GitHub Actions workflow will:
1. Build the APK from the `/android` directory
2. Extract version metadata from the built APK
3. Register the build with your Replit backend
4. Upload the APK as a GitHub artifact

## Prerequisites

1. **Android Project**: Located in `/android` folder (already configured)
2. **Replit Backend**: Your NexMDM backend must be running and accessible
3. **GitHub Repository**: This repository with the workflow file

## Step 1: Get Your Replit Backend URL

Your Replit app URL is available in the environment as `REPLIT_DOMAINS`. For this Repl, the URL is:

```
https://83b071bb-c5cb-4eda-b79c-d276873904c2-00-2ha4ytvejclnm.worf.replit.dev
```

**Important Notes**:
- Make sure both Backend and Frontend workflows are running before setting up GitHub Actions
- The public Replit URL routes to port 5000 (frontend), not port 8000 (backend)
- The workflow uses `/api/proxy/` to route through the frontend proxy to reach the backend
- This is the correct architecture for Replit's firewall/networking setup

## Step 2: Configure GitHub Secrets

You need to add two secrets to your GitHub repository:

### Navigate to Secrets

1. Go to your GitHub repository: `https://github.com/sergiogordon/unitymdm-prod`
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

## Step 3: Verify Workflow File

The workflow file is already configured at:
```
.github/workflows/build-and-register-apk.yml
```

This workflow will:
1. Trigger on pushes to `main` or `develop` branches (or manual trigger)
2. Build your Android debug APK from the `/android` directory
3. Extract metadata using `aapt` (version, size, SHA256 hash)
4. Register the build with your Replit backend
5. Upload the APK as a GitHub artifact (30-day retention)

### Key Features

- **Dynamic Versioning**: The Android app uses GitHub run numbers for version codes
- **Version Extraction**: Uses `aapt dump badging` to read actual APK metadata
- **Debug Keystore**: Automatically uses the GitHub Actions debug keystore
- **Error Handling**: Validates backend registration with proper HTTP status checks

## Step 4: Test the Workflow

### Trigger a Build

1. Make any commit to your `main` or `develop` branch:
   ```bash
   git add .
   git commit -m "Test APK build workflow"
   git push origin main
   ```

2. Or trigger manually:
   - Go to **Actions** tab in your GitHub repository
   - Click **Build and Register Debug APK** workflow
   - Click **Run workflow**
   - Select the branch
   - Click **Run workflow** button

### Monitor the Build

1. Go to **Actions** tab in your repository
2. Click on the running workflow
3. Watch the build progress in real-time

### Verify Registration

Once the workflow completes successfully:
1. Go to your NexMDM frontend: `https://83b071bb-c5cb-4eda-b79c-d276873904c2-00-2ha4ytvejclnm.worf.replit.dev/apk-management`
2. You should see the new build listed with:
   - Version name (e.g., `1.0.123-abc1234`)
   - Version code (auto-incremented from GitHub run number)
   - Build type: `debug`
   - File size
   - Upload time in CST
   - Git SHA
   - CI run ID

## Step 5: Troubleshooting

### Common Issues

#### Workflow fails with "chmod: cannot access './gradlew'"
- **Cause**: Workflow not updated to use `/android` directory
- **Solution**: Ensure workflow file matches the latest version in this repo

#### Backend registration fails with 401/403
- **Cause**: Admin key is incorrect or missing
- **Solution**: Verify `NEXMDM_ADMIN_KEY` secret matches your Replit `ADMIN_KEY`

#### Backend registration fails with connection error
- **Cause**: Backend is not running or URL is incorrect
- **Solution**: 
  - Check that your Replit backend is running
  - Verify `NEXMDM_BACKEND_URL` is correct and includes `https://`

#### Version extraction fails
- **Cause**: `aapt` not available or APK is malformed
- **Solution**: This should be rare on GitHub Actions runners (aapt is pre-installed)

### Check Workflow Logs

If the workflow fails:
1. Click on the failed workflow run in the **Actions** tab
2. Expand each step to see detailed logs
3. Look for error messages in:
   - "Build debug APK" step (for Gradle build errors)
   - "Get APK metadata" step (for version extraction errors)
   - "Register build with NexMDM backend" step (for API errors)

### Verify Secrets

To confirm secrets are set:
1. Go to **Settings** → **Secrets and variables** → **Actions**
2. You should see:
   - `NEXMDM_BACKEND_URL`
   - `NEXMDM_ADMIN_KEY`
3. You can update the values but cannot view them

## What Happens After Registration

Once a build is registered:

1. **Dashboard Display**: Build appears in `/apk-management` page
2. **Metadata Tracking**: All version info, checksums, and CI metadata are stored
3. **GitHub Artifact**: APK is downloadable from GitHub Actions for 30 days
4. **Download Link**: Currently points to GitHub Actions run page

## Version Numbering

The Android app uses smart versioning:
- **Version Code**: `GITHUB_RUN_NUMBER + 100` (auto-increments with each build)
- **Version Name**: `1.0.{versionCode}-{gitSha7}` (e.g., `1.0.123-abc1234`)

This ensures:
- Each build has a unique, increasing version code (required for Android updates)
- Version names are traceable to specific Git commits
- Local builds fall back to timestamp-based versioning

## Storage Notes

The current setup uses GitHub Artifacts for APK storage (free for 30 days). For production:

- Consider uploading APKs to S3, Google Cloud Storage, or Backblaze B2
- Update the `storage_url` in the workflow to point to the cloud storage URL
- Implement actual file upload before registering with the backend
- Update the download endpoint to fetch from cloud storage

## Security

- **Never commit secrets** to your repository
- Always use GitHub Secrets for sensitive values
- Rotate your `ADMIN_KEY` periodically
- Review workflow runs for any exposed credentials
- GitHub Actions logs are public for public repositories

## Next Steps

Once builds are appearing in your dashboard:
- View build history and track version progression
- Monitor which Git commits produced which APKs
- Track APK sizes and identify bloat
- Use registered builds for OTA updates to your device fleet
- Set up release builds with proper signing keys
