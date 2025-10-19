# GitHub Actions Workflow Setup - Android CI/CD

## ✅ What Was Fixed

The GitHub Actions workflow was looking for Android code at `UNITYmdm/android/` but your actual project structure uses just `android/`. All paths have been corrected.

## 📋 How to Deploy This Fix

### Option 1: Copy from Replit to GitHub (Recommended)

1. **In your GitHub repository**, navigate to `.github/workflows/`
2. **Edit or create** `android-ci.yml`
3. **Copy the entire contents** from this Replit project's `.github/workflows/android-ci.yml`
4. **Commit and push** the changes

### Option 2: Git Push from Replit (If Git is configured)

```bash
git add .github/workflows/android-ci.yml
git commit -m "Fix Android workflow paths (UNITYmdm/android -> android)"
git push origin main
```

## 🔑 Required GitHub Secrets

For the workflow to build and sign APKs, configure these secrets in your GitHub repository:

### Required Secrets:
1. **`ANDROID_KEYSTORE_BASE64`** - Your Android signing keystore encoded in base64
2. **`KEYSTORE_PASSWORD`** - Password for the keystore
3. **`ANDROID_KEY_ALIAS`** - Key alias in the keystore
4. **`ANDROID_KEY_ALIAS_PASSWORD`** - Password for the key alias

### Optional Secrets (for backend upload):
5. **`BACKEND_URL`** - Your NexMDM backend URL (e.g., `https://your-repl.replit.dev`)
6. **`ADMIN_KEY`** - Admin API key for uploading APKs to your backend

## 📦 What the Workflow Does

✅ Builds **Debug APK** (with release signing)  
✅ Builds **Release APK** (production-ready)  
✅ Builds **Release AAB** (for Play Store)  
✅ Verifies APK signatures with `apksigner`  
✅ Calculates SHA256 checksums  
✅ Uploads Debug APK to your NexMDM backend (optional)  
✅ Uploads all artifacts to GitHub (30-90 day retention)  
✅ Generates detailed build summary  

## 🔒 Security Features

- Keystore is decoded from base64 secret
- Keystore is automatically cleaned up after build
- All APKs signed with your release keystore for consistent upgrades
- Signature verification ensures APK integrity

## 🚀 Triggering Builds

The workflow runs automatically when:
- ✅ You push changes to `main` branch that affect `android/**` files
- ✅ You create a pull request affecting Android code
- ✅ You manually trigger it from the GitHub Actions tab

## 🎯 Next Steps

1. **Copy the corrected workflow** to your GitHub repository
2. **Configure the required secrets** in GitHub Settings → Secrets
3. **Push a change** to `android/` to trigger a build
4. **Download the APK** from the GitHub Actions artifacts

## 📊 Build Artifacts

After a successful build, you'll find:

- **Debug APK**: 30-day retention, uploaded to backend
- **Release APK**: 90-day retention  
- **Release AAB**: 90-day retention (for Play Store)

All with SHA256 checksums and verified signatures!

---

**Questions?** The workflow includes detailed logs for each step. Check the GitHub Actions tab for build progress and troubleshooting.
