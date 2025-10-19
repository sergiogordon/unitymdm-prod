# Building the NexMDM Android App

## Option 1: Automatic Build with GitHub Actions (Recommended) 🚀

This repository includes a GitHub Actions workflow that **automatically builds AND uploads** the APK:

1. **First-time setup** (one-time only):
   - See [GitHub Actions Setup Guide](../.github/GITHUB_ACTIONS_SETUP.md)
   - Configure two secrets: `NEXMDM_API_URL` and `ADMIN_KEY`

2. **Push your code to GitHub**:
   ```bash
   git add .
   git commit -m "Update Android app"
   git push origin main
   ```

3. **GitHub Actions automatically**:
   - ✅ Builds the APK
   - ✅ Extracts metadata (package name, version)
   - ✅ **Uploads to your NexMDM backend** (if secrets configured)
   - ✅ Commits APK to `downloads/nexmdm.apk`

4. **APK appears in your dashboard** ready to deploy to devices!

**No more manual downloading/uploading!** The APK is automatically uploaded to your backend and available in the dashboard for deployment.

## Option 2: Build Locally with Android Studio

If you have Android Studio installed:

1. **Open the project**:
   ```bash
   cd android
   ```
   - Open this folder in Android Studio
   - Wait for Gradle sync to complete

2. **Build the APK**:
   - Click Build → Build Bundle(s) / APK(s) → Build APK(s)
   - Or use the command line:
     ```bash
     ./gradlew assembleDebug
     ```

3. **Copy the APK**:
   ```bash
   cp app/build/outputs/apk/debug/app-debug.apk ../downloads/nexmdm.apk
   ```

## Option 3: Command Line Build (Linux/Mac)

If you have the Android SDK installed:

1. **Set ANDROID_HOME**:
   ```bash
   export ANDROID_HOME=$HOME/Android/Sdk
   ```

2. **Build**:
   ```bash
   cd android
   ./gradlew assembleDebug
   cp app/build/outputs/apk/debug/app-debug.apk ../downloads/nexmdm.apk
   ```

## Verifying the Build

After building, verify the APK exists:
```bash
ls -lh downloads/nexmdm.apk
```

The Install QR code in your dashboard will then work correctly!

## Troubleshooting

### "SDK location not found"
- Make sure ANDROID_HOME is set
- Or create `android/local.properties`:
  ```
  sdk.dir=/path/to/your/Android/Sdk
  ```

### "Command not found: gradlew"
- Run `gradle wrapper` first to generate the wrapper files

### GitHub Actions Build Fails
- Check the Actions tab for detailed logs
- Ensure all Android code compiles without errors
