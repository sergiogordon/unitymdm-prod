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

You need to add **five** secrets to your GitHub repository for the full build and deploy workflow:

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

#### Secret 3: ANDROID_KEYSTORE_BASE64

- **Name**: `ANDROID_KEYSTORE_BASE64`
- **Value**: Base64-encoded Android keystore file

To create this:
```bash
base64 -w 0 /path/to/your/release.keystore > keystore.txt
```
Then copy the contents of `keystore.txt` as the secret value.

#### Secret 4: KEYSTORE_PASSWORD

- **Name**: `KEYSTORE_PASSWORD`
- **Value**: Your keystore password

#### Secret 5: ANDROID_KEY_ALIAS

- **Name**: `ANDROID_KEY_ALIAS`
- **Value**: Your key alias (e.g., `key0`)

#### Secret 6: ANDROID_KEY_ALIAS_PASSWORD

- **Name**: `ANDROID_KEY_ALIAS_PASSWORD`
- **Value**: Your key alias password

## Step 3: Verify Workflow File

The workflow file is configured at:
```
.github/workflows/android-build-and-deploy.yml
```

This unified workflow will:
1. Trigger on pushes to `main` or `develop` branches, version tags, or manual trigger
2. Build debug APK (signed with release keystore)
3. Build release APK and AAB (signed with release keystore)
4. Verify all signatures with `apksigner`
5. Extract metadata using `aapt` and `keytool`
6. Register the debug build with your Replit backend
7. Upload all artifacts to GitHub (debug: 30 days, release: 90 days)

### Key Features

- **Unified Workflow**: Single workflow for all build types (replaces old `android-ci.yml` and `build-and-register-apk.yml`)
- **Production Signing**: All builds signed with your release keystore
- **Dynamic Versioning**: Uses GitHub run numbers for version codes
- **Signature Verification**: Validates all APKs before upload
- **Backend Integration**: Automatically registers debug builds in APK Management system
- **Comprehensive Artifacts**: Debug APK, Release APK, and Release AAB

### Workflow Consolidation

**Note**: If you still have the old workflow files, you can safely delete them:
- `.github/workflows/android-ci.yml` (OLD - replaced)
- `.github/workflows/build-and-register-apk.yml` (OLD - replaced)

The new `android-build-and-deploy.yml` combines all functionality from both workflows.

## Step 4: Test the Workflow

### Trigger a Build

1. Make any commit to your `main` or `develop` branch:
   ```bash
   git add .
   git commit -m "Test unified build workflow"
   git push origin main
   ```

2. Or trigger manually:
   - Go to **Actions** tab in your GitHub repository
   - Click **Android Build and Deploy** workflow
   - Click **Run workflow**
   - Select the branch
   - Click **Run workflow** button

3. Or tag a release:
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```

### Monitor the Build

1. Go to **Actions** tab in your repository
2. Click on the running workflow
3. Watch the build progress in real-time
4. Expected duration: 10-15 minutes

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
   - Signer fingerprint

## Step 5: Troubleshooting

### Common Issues

#### Workflow fails with "chmod: cannot access './gradlew'"
- **Cause**: Workflow not updated to use `/android` directory
- **Solution**: Ensure you're using the latest `android-build-and-deploy.yml`

#### Backend registration fails with 401/403
- **Cause**: Admin key is incorrect or missing
- **Solution**: Verify `NEXMDM_ADMIN_KEY` secret matches your Replit `ADMIN_KEY`

#### Backend registration fails with connection error
- **Cause**: Backend is not running or URL is incorrect
- **Solution**: 
  - Check that your Replit backend is running
  - Verify `NEXMDM_BACKEND_URL` is correct and includes `https://`

#### APK signature verification fails
- **Cause**: Keystore secrets are incorrect or corrupted
- **Solution**: 
  - Re-generate the base64 keystore with `base64 -w 0`
  - Verify keystore password and key alias are correct
  - Test keystore locally first

#### Build fails with "keystore not found"
- **Cause**: `ANDROID_KEYSTORE_BASE64` secret is missing or invalid
- **Solution**: Verify the secret contains valid base64-encoded keystore data

### Check Workflow Logs

If the workflow fails:
1. Click on the failed workflow run in the **Actions** tab
2. Expand each step to see detailed logs
3. Look for error messages in:
   - "Build Debug APK" / "Build Release APK" (for Gradle build errors)
   - "Verify APK signatures" (for signing errors)
   - "Register build with NexMDM backend" (for API errors)

### Verify Secrets

To confirm secrets are set:
1. Go to **Settings** → **Secrets and variables** → **Actions**
2. You should see:
   - `NEXMDM_BACKEND_URL`
   - `NEXMDM_ADMIN_KEY`
   - `ANDROID_KEYSTORE_BASE64`
   - `KEYSTORE_PASSWORD`
   - `ANDROID_KEY_ALIAS`
   - `ANDROID_KEY_ALIAS_PASSWORD`
3. You can update the values but cannot view them

## What Happens After Registration

Once a build is registered:

1. **Dashboard Display**: Build appears in `/apk-management` page
2. **Metadata Tracking**: All version info, checksums, and CI metadata are stored
3. **GitHub Artifacts**: 
   - Debug APK: 30 days retention
   - Release APK: 90 days retention
   - Release AAB: 90 days retention
4. **Download Link**: Links to GitHub Actions artifacts page

## Version Numbering

The Android app uses smart versioning:
- **Version Code**: `GITHUB_RUN_NUMBER + 100` (auto-increments with each build)
- **Version Name**: 
  - For tags: Uses the tag name (e.g., `v1.0.0`)
  - For commits: `1.0.{versionCode}-{gitSha7}` (e.g., `1.0.123-abc1234`)

This ensures:
- Each build has a unique, increasing version code (required for Android updates)
- Version names are traceable to specific Git commits or releases
- Tagged releases have clean version names
- Local builds fall back to timestamp-based versioning

## Build Artifacts

The workflow produces three artifacts:

1. **Debug APK** (`nexmdm-debug-apk-{version_code}`)
   - Signed with release keystore
   - Registered in APK Management system
   - 30-day GitHub retention
   - Use for testing and OTA updates

2. **Release APK** (`nexmdm-release-apk-{version_code}`)
   - Production-ready
   - 90-day GitHub retention
   - Use for sideloading or direct distribution

3. **Release AAB** (`nexmdm-release-aab-{version_code}`)
   - Google Play bundle format
   - 90-day GitHub retention
   - Use for Play Store uploads

## Security

- **Never commit secrets** to your repository
- Always use GitHub Secrets for sensitive values
- Rotate your `ADMIN_KEY` periodically
- Review workflow runs for any exposed credentials
- GitHub Actions logs are public for public repositories
- Keystore is automatically cleaned up after each workflow run

## Next Steps

Once builds are appearing in your dashboard:
- View build history and track version progression
- Monitor which Git commits produced which APKs
- Track APK sizes and identify bloat
- Use registered builds for OTA updates to your device fleet
- Download release artifacts for production deployment
- Tag releases for clean version names (e.g., `v1.0.0`, `v1.1.0`)
