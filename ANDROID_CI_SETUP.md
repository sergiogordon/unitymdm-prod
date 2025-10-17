# Android Agent CI/CD Setup Guide

This guide explains how to configure and use the automated Android CI/CD pipeline for the NexMDM agent.

## Overview

The GitHub Actions workflow automatically builds, signs, verifies, and distributes the NexMDM Android agent on every commit to `main` and on version tags (`v*`).

### What Gets Automated

- ✅ Debug APK builds (auto-uploaded to APK Management backend)
- ✅ Release APK builds (uploaded as GitHub artifacts)
- ✅ Release AAB builds (uploaded as GitHub artifacts)
- ✅ APK signature verification
- ✅ Automatic versioning based on commit count
- ✅ SHA256 checksum generation
- ✅ Build metadata tracking

## Required GitHub Secrets

You must configure the following secrets in your GitHub repository settings (`Settings > Secrets and variables > Actions`):

### 1. `ANDROID_KEYSTORE_BASE64`

Your Android release keystore encoded as base64.

**How to create:**

```bash
# If you already have a keystore (e.g., release.keystore):
base64 -w 0 release.keystore > release.keystore.b64

# Or create a new keystore first:
keytool -genkey -v \
  -keystore release.keystore \
  -alias nexmdm \
  -keyalg RSA \
  -keysize 2048 \
  -validity 10000 \
  -storepass YOUR_STORE_PASSWORD \
  -keypass YOUR_KEY_PASSWORD

# Then encode it:
base64 -w 0 release.keystore > release.keystore.b64
```

Copy the contents of `release.keystore.b64` and add it as the `ANDROID_KEYSTORE_BASE64` secret.

### 2. `KEYSTORE_PASSWORD`

The password for your keystore file (same as `-storepass` above).

### 3. `ANDROID_KEY_ALIAS`

The alias of your signing key (e.g., `nexmdm` from the example above).

### 4. `ANDROID_KEY_ALIAS_PASSWORD`

The password for your signing key (same as `-keypass` above).

### 5. `BACKEND_URL`

The URL of your NexMDM backend API where debug APKs will be uploaded.

**Example:** `https://your-backend.replit.dev`

### 6. `ADMIN_KEY`

The admin API key for authenticating APK uploads to your backend.

You can generate this or retrieve it from your backend's environment variables.

## Workflow Triggers

The CI workflow runs automatically on:

### 1. Push to `main` branch
```bash
git push origin main
```

### 2. Version tags
```bash
# Tag a release version
git tag v1.0.5
git push origin v1.0.5
```

### 3. Manual trigger
Navigate to `Actions > Android Agent CI > Run workflow` in GitHub.

## Versioning Strategy

### Version Code
- Calculated as: `GITHUB_RUN_NUMBER + 100`
- Increments automatically with each CI run
- Ensures uniqueness and proper upgrade paths

### Version Name
- **For tagged releases:** Uses the tag name (e.g., `v1.0.5`)
- **For commits:** Uses format `1.0.{versionCode}-{commitHash}` (e.g., `1.0.156-a3b2c1d`)

## Build Outputs

### Debug APK
- **Purpose:** Internal testing and device enrollment
- **Signing:** Signed with release keystore (for consistent upgrades)
- **Distribution:** Auto-uploaded to APK Management backend
- **Retention:** 30 days as GitHub artifact

### Release APK
- **Purpose:** Production deployment
- **Signing:** Signed with release keystore
- **Distribution:** Available as GitHub artifact
- **Retention:** 90 days as GitHub artifact

### Release AAB (Android App Bundle)
- **Purpose:** Google Play Store distribution (if needed)
- **Signing:** Signed with release keystore
- **Distribution:** Available as GitHub artifact
- **Retention:** 90 days as GitHub artifact

## Security Features

### Keystore Protection
- Keystore stored only in GitHub Secrets (base64 encoded)
- Decoded securely at runtime in CI environment
- Automatically cleaned up after build
- Never committed to repository

### Signature Verification
- All APKs verified with `apksigner` before upload
- Verification output included in job logs
- Build fails if signature verification fails

### Secret Management
- All sensitive values injected from GitHub Secrets
- No secrets printed in CI logs
- Environment variables cleared after use

## Build Artifacts

### Downloading Artifacts

1. Navigate to `Actions > Android Agent CI > [workflow run]`
2. Scroll to "Artifacts" section
3. Download the desired artifact:
   - `nexmdm-debug-apk-{versionCode}`
   - `nexmdm-release-apk-{versionCode}`
   - `nexmdm-release-aab-{versionCode}`

### Artifact Contents

Each artifact includes:
- The compiled APK/AAB file
- SHA256 checksum (in job summary)
- Signature verification status

## Build Summary

Each workflow run generates a detailed summary including:

- Version code and version name
- Commit hash and build timestamp
- SHA256 checksums for all artifacts
- Signature verification results
- Backend upload status
- Download links for artifacts

Access the summary at: `Actions > [workflow run] > Summary`

## Troubleshooting

### Build Fails: "Release keystore not found in CI"

**Cause:** `ANDROID_KEYSTORE_BASE64` secret is missing or invalid.

**Solution:**
1. Verify the secret is set in repository settings
2. Ensure the base64 encoding has no line breaks (`-w 0` flag)
3. Re-encode and update the secret if needed

### Build Fails: "Signature verification failed"

**Cause:** Keystore credentials (password, alias, key password) are incorrect.

**Solution:**
1. Verify all four keystore secrets are correct
2. Test locally with the same credentials:
   ```bash
   cd UNITYmdm/android
   KEYSTORE_FILE=../../release.keystore \
   KEYSTORE_PASSWORD=your_password \
   KEY_ALIAS=your_alias \
   KEY_PASSWORD=your_key_password \
   ./gradlew assembleRelease
   ```

### Backend Upload Fails

**Cause:** `BACKEND_URL` or `ADMIN_KEY` is incorrect.

**Solution:**
1. Verify the backend URL is accessible
2. Test the API key manually:
   ```bash
   curl -X POST "https://your-backend.replit.dev/v1/apk/upload" \
     -H "X-Admin-Key: your_api_key" \
     -F "file=@test.apk" \
     -F "package_name=com.nexmdm" \
     -F "version_name=test" \
     -F "version_code=1"
   ```

**Note:** Backend upload failure is non-critical and won't fail the entire workflow.

### Version Code Not Incrementing

**Cause:** Workflow is being re-run on the same run number.

**Solution:** Push a new commit or create a new tag to trigger a fresh workflow run.

## Performance Targets

### Build Time
- **Target:** ≤5 minutes on standard GitHub runners
- **Typical:** 3-4 minutes with Gradle caching

### Success Rate
- **Target:** 100% for commits with valid secrets
- Monitor failed runs and investigate immediately

### Reproducibility
- Builds from the same commit produce identical checksums
- Gradle caching ensures consistent dependency resolution

## Integration with APK Management

### Automatic Upload

Debug APKs are automatically uploaded to the backend `/v1/apk/upload` endpoint with:

```json
{
  "package_name": "com.nexmdm",
  "version_name": "1.0.156-a3b2c1d",
  "version_code": 156,
  "notes": "Auto-built by CI from commit a3b2c1d | Build #56 | Built at 2025-01-15T10:30:00Z"
}
```

### Viewing in Dashboard

1. Log into the NexMDM dashboard
2. Navigate to "APK Management" page
3. See the latest CI-built debug APK
4. Deploy to devices with one click

## Best Practices

### Tagging Releases

```bash
# Create an annotated tag for important releases
git tag -a v1.0.5 -m "Release version 1.0.5 - Bug fixes and improvements"
git push origin v1.0.5
```

### Monitoring Builds

1. Enable GitHub notifications for workflow failures
2. Review job summaries for each build
3. Verify checksums match when downloading artifacts

### Keystore Backup

⚠️ **CRITICAL:** Keep a secure backup of your `release.keystore` file!

- Store it in a password manager or secure vault
- Never commit it to the repository
- If lost, you cannot update existing app installations

## Quick Start Checklist

- [ ] Generate or obtain release keystore
- [ ] Encode keystore to base64
- [ ] Add all 6 required secrets to GitHub repository
- [ ] Test workflow with a commit to main
- [ ] Verify debug APK appears in backend
- [ ] Download and test release APK artifact
- [ ] Tag a version and verify versioning works

## Support

For issues with the CI pipeline:

1. Check the workflow run logs in GitHub Actions
2. Review the build summary for error details
3. Verify all secrets are correctly configured
4. Test the build locally with the same credentials

For backend integration issues:

1. Check backend logs for upload errors
2. Verify API endpoint is accessible
3. Test API key authentication manually
