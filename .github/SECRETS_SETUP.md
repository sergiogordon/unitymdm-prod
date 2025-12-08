# GitHub Secrets Setup - Quick Reference

This file contains instructions for setting up the required GitHub Secrets for the Android CI/CD pipeline.

## Required Secrets

Configure these in: **Settings → Secrets and variables → Actions → New repository secret**

### 1. ANDROID_KEYSTORE_BASE64
**What:** Base64-encoded Android release keystore file  
**How to create:**
```bash
# Option 1: If you have an existing keystore
base64 -w 0 release.keystore > release.keystore.b64

# Option 2: Create a new keystore first
keytool -genkey -v \
  -keystore release.keystore \
  -alias nexmdm \
  -keyalg RSA \
  -keysize 2048 \
  -validity 10000 \
  -storepass YOUR_STORE_PASSWORD \
  -keypass YOUR_KEY_PASSWORD

# Then encode it
base64 -w 0 release.keystore > release.keystore.b64
```
**Secret value:** Contents of `release.keystore.b64` file

---

### 2. KEYSTORE_PASSWORD
**What:** Password for the keystore file  
**Secret value:** The `-storepass` value from keystore creation (e.g., `mySecureStorePass123`)

---

### 3. ANDROID_KEY_ALIAS
**What:** The alias name of your signing key  
**Secret value:** The `-alias` value from keystore creation (e.g., `nexmdm`)

---

### 4. ANDROID_KEY_ALIAS_PASSWORD
**What:** Password for the signing key  
**Secret value:** The `-keypass` value from keystore creation (e.g., `mySecureKeyPass456`)

---

### 5. NEXMDM_BACKEND_URL_DEV
**What:** URL of your development NexMDM backend API  
**Secret value:** Your dev backend URL (e.g., `https://your-dev-repl.replit.dev`)  
**Note:** This is optional - if not set, dev uploads will be skipped

---

### 6. NEXMDM_BACKEND_URL_PROD
**What:** URL of your production NexMDM backend API  
**Secret value:** Your prod backend URL (e.g., `https://unitymdm.replit.app`)  
**Note:** This is optional - if not set, prod uploads will be skipped. At least one backend URL must be configured.

---

### 7. NEXMDM_ADMIN_KEY
**What:** Admin API key for uploading APKs to backends  
**Secret value:** Your backend admin key (check backend environment variables)  
**Note:** This key is used for both dev and prod backends

---

## Quick Setup Checklist

- [ ] Generate or locate your release keystore
- [ ] Encode keystore to base64 (no line breaks!)
- [ ] Add `ANDROID_KEYSTORE_BASE64` secret
- [ ] Add `KEYSTORE_PASSWORD` secret
- [ ] Add `ANDROID_KEY_ALIAS` secret
- [ ] Add `ANDROID_KEY_ALIAS_PASSWORD` secret
- [ ] Add `NEXMDM_BACKEND_URL_DEV` secret (optional, for dev deployments)
- [ ] Add `NEXMDM_BACKEND_URL_PROD` secret (optional, for prod deployments)
- [ ] Add `NEXMDM_ADMIN_KEY` secret (required if any backend URL is set)
- [ ] Test by pushing to main branch
- [ ] Verify workflow runs successfully and uploads to both backends

## Testing Your Setup

1. **Push to main:**
   ```bash
   git add .
   git commit -m "Test CI pipeline"
   git push origin main
   ```

2. **Check workflow:**
   - Go to Actions tab in GitHub
   - Click on the latest "Android Agent CI" run
   - Verify all steps complete successfully

3. **Verify outputs:**
   - Debug APK uploaded to backend ✅
   - Release APK in workflow artifacts ✅
   - Build summary shows checksums ✅

## Troubleshooting

### ❌ "Release keystore not found in CI"
→ Check `ANDROID_KEYSTORE_BASE64` is set and has no line breaks

### ❌ "Signature verification failed"
→ Verify keystore password, alias, and key password are correct

### ⚠️ Backend upload fails
→ Check `BACKEND_URL` and `ADMIN_KEY` values

## Security Notes

- ✅ Keystore is only in GitHub Secrets (base64 encoded)
- ✅ Keystore is decoded at runtime and cleaned up after build
- ✅ No secrets are printed in CI logs
- ✅ Keystore file is **never** committed to repository
- ⚠️ **BACKUP YOUR KEYSTORE!** If lost, you cannot update existing installations

## Next Steps

Once secrets are configured:
1. CI will automatically build on every push to `main`
2. Debug APKs will be uploaded to your backend
3. Release APKs will be available in GitHub Actions artifacts
4. You can deploy to devices via the dashboard

For more details, see [ANDROID_CI_SETUP.md](../ANDROID_CI_SETUP.md)
