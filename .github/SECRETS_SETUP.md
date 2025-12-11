# GitHub Secrets Setup - Quick Reference

This file contains instructions for setting up the required GitHub Secrets for the Android CI/CD pipeline.

## Required Secrets

Configure these in: **Settings → Secrets and variables → Actions → New repository secret**

### Android Signing Secrets

#### 1. ANDROID_KEYSTORE_BASE64
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

#### 2. KEYSTORE_PASSWORD
**What:** Password for the keystore file  
**Secret value:** The `-storepass` value from keystore creation (e.g., `mySecureStorePass123`)

---

#### 3. ANDROID_KEY_ALIAS
**What:** The alias name of your signing key  
**Secret value:** The `-alias` value from keystore creation (e.g., `nexmdm`)

---

#### 4. ANDROID_KEY_ALIAS_PASSWORD
**What:** Password for the signing key  
**Secret value:** The `-keypass` value from keystore creation (e.g., `mySecureKeyPass456`)

---

### Development Environment Secrets (Optional)

#### 5. NEXMDM_BACKEND_URL
**What:** URL of your development NexMDM backend  
**Secret value:** Your dev backend URL (e.g., `https://your-project.replit.dev`)  
**Note:** If not set, dev upload will be skipped (prod upload will still happen)

---

#### 6. NEXMDM_ADMIN_KEY
**What:** Admin API key for your development backend  
**Secret value:** Your dev backend admin key (check backend environment variables)

---

### Production Environment Secrets (REQUIRED)

#### 7. NEXMDM_PROD_URL
**What:** URL of your production NexMDM backend  
**Secret value:** Your production URL (e.g., `https://unitymdm.replit.app`)  
**REQUIRED:** The workflow will fail if this is not set

---

#### 8. NEXMDM_PROD_ADMIN_KEY
**What:** Admin API key for your production backend  
**Secret value:** Your production backend admin key  
**REQUIRED:** The workflow will fail if this is not set

---

## Quick Setup Checklist

### Android Signing (Required)
- [ ] Generate or locate your release keystore
- [ ] Encode keystore to base64 (no line breaks!)
- [ ] Add `ANDROID_KEYSTORE_BASE64` secret
- [ ] Add `KEYSTORE_PASSWORD` secret
- [ ] Add `ANDROID_KEY_ALIAS` secret
- [ ] Add `ANDROID_KEY_ALIAS_PASSWORD` secret

### Production Deployment (Required)
- [ ] Add `NEXMDM_PROD_URL` secret (e.g., `https://unitymdm.replit.app`)
- [ ] Add `NEXMDM_PROD_ADMIN_KEY` secret

### Development Deployment (Optional)
- [ ] Add `NEXMDM_BACKEND_URL` secret (your dev Replit URL)
- [ ] Add `NEXMDM_ADMIN_KEY` secret

### Verification
- [ ] Test by pushing to main branch
- [ ] Verify workflow runs successfully
- [ ] Check APK appears in production APK Management page

## Testing Your Setup

1. **Push to main:**
   ```bash
   git add .
   git commit -m "Test CI pipeline"
   git push origin main
   ```

2. **Check workflow:**
   - Go to Actions tab in GitHub
   - Click on the latest "Android Build and Deploy" run
   - Verify all steps complete successfully

3. **Verify outputs:**
   - APK uploaded to PRODUCTION environment
   - APK uploaded to DEV environment (if configured)
   - Release APK in workflow artifacts
   - Build summary shows checksums

## Troubleshooting

### ❌ "Release keystore not found in CI"
→ Check `ANDROID_KEYSTORE_BASE64` is set and has no line breaks

### ❌ "Signature verification failed"
→ Verify keystore password, alias, and key password are correct

### ❌ "NEXMDM_PROD_URL secret is not set"
→ Add `NEXMDM_PROD_URL` with your production URL (e.g., `https://unitymdm.replit.app`)

### ❌ "NEXMDM_PROD_ADMIN_KEY secret is not set"
→ Add `NEXMDM_PROD_ADMIN_KEY` with your production admin key

### ⚠️ Production upload fails with 404
→ Make sure the production app is deployed and running

### ⚠️ Dev upload skipped
→ This is OK if you only want to deploy to production. Add `NEXMDM_BACKEND_URL` and `NEXMDM_ADMIN_KEY` to also upload to dev.

## Dual Environment Deployment

The CI/CD pipeline now deploys to **both** environments:

1. **Development** (optional): Uploads to your Replit dev URL
   - Uses `NEXMDM_BACKEND_URL` and `NEXMDM_ADMIN_KEY`
   - Skipped if not configured (workflow continues)

2. **Production** (required): Uploads to your production URL
   - Uses `NEXMDM_PROD_URL` and `NEXMDM_PROD_ADMIN_KEY`
   - Workflow fails if not configured

## Security Notes

- Keystore is only in GitHub Secrets (base64 encoded)
- Keystore is decoded at runtime and cleaned up after build
- No secrets are printed in CI logs
- Keystore file is **never** committed to repository
- **BACKUP YOUR KEYSTORE!** If lost, you cannot update existing installations

## Migrating Existing APKs to Production

If you have APKs in your dev environment that need to be copied to production, use the migration script:

```bash
# From your dev Replit environment
cd server
python scripts/migrate_apks_to_prod.py \
  --prod-url https://unitymdm.replit.app \
  --prod-admin-key YOUR_PROD_ADMIN_KEY

# Dry run first to see what would be migrated
python scripts/migrate_apks_to_prod.py \
  --prod-url https://unitymdm.replit.app \
  --prod-admin-key YOUR_PROD_ADMIN_KEY \
  --dry-run
```

## Next Steps

Once secrets are configured:
1. CI will automatically build on every push to `main`
2. Release APKs will be uploaded to both DEV and PRODUCTION
3. Release APKs will also be available in GitHub Actions artifacts
4. You can deploy to devices via the dashboard in either environment

For more details, see [ANDROID_CI_SETUP.md](../ANDROID_CI_SETUP.md)
