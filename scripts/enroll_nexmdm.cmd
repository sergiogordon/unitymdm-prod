@echo off
setlocal enabledelayedexpansion

REM ====== CONFIG ======
REM Update these values before using:
REM   - BASE_URL: Your NexMDM server URL
REM   - ADMIN_KEY: Your admin key from Settings page (never expires)
REM   - ALIAS: Device alias name
set PKG=com.nexmdm
set ALIAS=test
set APK_PATH=%TEMP%\nexmdm-latest.apk
set BASE_URL=https://83b071bb-c5cb-4eda-b79c-d276873904c2-00-2ha4ytvejclnm.worf.replit.dev
set DL_URL=%BASE_URL%/v1/apk/download-latest
set ADMIN_KEY=YOUR_ADMIN_KEY_HERE
set MIN_SDK=30

echo [NexMDM Deployment - Device: %ALIAS%]
echo.

echo [Step 0] Checking prerequisites...
where adb >nul 2>&1
if errorlevel 1 (
    echo ❌ ADB not found in PATH
    echo    Fix: Install Android Platform Tools and add to PATH
    echo    Download: https://developer.android.com/tools/releases/platform-tools
    exit /b 1
)
echo ✅ ADB found
echo.

echo [Step 1/8] Waiting for device...
adb wait-for-device
if errorlevel 1 (
    echo ❌ No device found
    echo    Fix: Check USB cable, ensure USB debugging enabled
    exit /b 2
)
echo ✅ Device connected
echo.

echo [Step 2/8] Checking Android version compatibility...
for /f "tokens=*" %%A in ('adb shell getprop ro.build.version.sdk 2^>nul') do set DEVICE_SDK=%%A
set DEVICE_SDK=%DEVICE_SDK: =%
for /f "tokens=*" %%A in ('adb shell getprop ro.build.version.release 2^>nul') do set DEVICE_VER=%%A
set DEVICE_VER=%DEVICE_VER: =%

echo    Device SDK: %DEVICE_SDK% (Android %DEVICE_VER%)
echo    Required: SDK %MIN_SDK%+ (Android 11+)

if "%DEVICE_SDK%"=="" (
    echo ❌ Could not detect device SDK version
    exit /b 2
)

if %DEVICE_SDK% LSS %MIN_SDK% (
    echo.
    echo ❌ INCOMPATIBLE DEVICE
    echo    This device runs Android %DEVICE_VER% (SDK %DEVICE_SDK%)
    echo    NexMDM requires Android 11+ (SDK 30+)
    echo.
    echo    Options:
    echo    1. Use a device with Android 11 or newer
    echo    2. Update this device's OS if possible
    exit /b 2
)
echo ✅ Android version compatible
echo.

echo [Step 3/8] Downloading latest APK...
echo    URL: %DL_URL%
curl -L -H "X-Admin-Key: %ADMIN_KEY%" "%DL_URL%" -o "%APK_PATH%" 2>&1
if errorlevel 1 (
    echo ❌ Download failed
    echo    Fix: Check network connection and ADMIN_KEY
    exit /b 3
)
if not exist "%APK_PATH%" (
    echo ❌ APK missing at %APK_PATH%
    exit /b 3
)

REM Verify APK size (should be > 500KB)
for %%A in ("%APK_PATH%") do set APK_SIZE=%%~zA
if %APK_SIZE% LSS 500000 (
    echo ❌ APK file too small (%APK_SIZE% bytes) - likely auth error
    echo    Fix: Verify your ADMIN_KEY is correct
    type "%APK_PATH%"
    exit /b 3
)
echo ✅ APK downloaded (%APK_SIZE% bytes)
echo.

echo [Step 4/8] Installing APK...
adb install -r -g "%APK_PATH%" 2>&1
if errorlevel 1 (
    echo    Retry: Uninstalling existing version...
    adb uninstall %PKG% >nul 2>&1
    adb install -r -g -t "%APK_PATH%" 2>&1
    if errorlevel 1 (
        echo ❌ Install failed
        echo    Common causes:
        echo    - Device storage full
        echo    - APK corrupted during download
        echo    - Signature mismatch with existing install
        exit /b 4
    )
)
echo ✅ APK installed
echo.

echo [Step 5/8] Setting Device Owner...
for /f "tokens=2 delims=: " %%A in ('adb shell settings get secure device_provisioned') do set DEVPROV=%%A
for /f "tokens=2 delims=: " %%A in ('adb shell settings get secure user_setup_complete') do set USERSETUP=%%A
set DEVPROV=%DEVPROV:~0,1%
set USERSETUP=%USERSETUP:~0,1%

adb shell dumpsys device_policy | findstr /C:"Device Owner" /C:"%PKG%" >nul
if errorlevel 1 (
    echo    Device Owner not detected, setting up...
    if "%DEVPROV%"=="1" if "%USERSETUP%"=="1" (
        echo ❌ Cannot set Device Owner on a provisioned device
        echo    Fix: Factory reset the device and try again
        exit /b 5
    )
    adb shell dpm set-device-owner %PKG%/.NexDeviceAdminReceiver 2>&1
    if errorlevel 1 (
        echo ❌ Device Owner setup failed
        echo    Fix: Factory reset device and ensure no accounts are added
        exit /b 6
    )
)

adb shell dumpsys device_policy | findstr /C:"%PKG%" >nul
if errorlevel 1 (
    echo ❌ Device Owner verification failed
    exit /b 7
)
echo ✅ Device Owner confirmed
echo.

echo [Step 6/8] Granting permissions...
adb shell pm grant %PKG% android.permission.POST_NOTIFICATIONS 2>nul
adb shell pm grant %PKG% android.permission.CAMERA 2>nul
adb shell pm grant %PKG% android.permission.ACCESS_FINE_LOCATION 2>nul
adb shell appops set %PKG% RUN_ANY_IN_BACKGROUND allow 2>nul
adb shell appops set %PKG% AUTO_REVOKE_PERMISSIONS_IF_UNUSED ignore 2>nul
adb shell appops set %PKG% GET_USAGE_STATS allow 2>nul
adb shell dumpsys deviceidle whitelist +%PKG% >nul
echo ✅ Permissions granted
echo.

echo [Step 7/8] Applying optimizations...
adb shell "settings put global app_standby_enabled 0; settings put global adaptive_battery_management_enabled 0; settings put global stay_on_while_plugged_in 7" >nul 2>&1
adb shell cmd deviceidle whitelist +com.unitynetwork.unityapp >nul 2>&1
adb shell appops set com.unitynetwork.unityapp RUN_ANY_IN_BACKGROUND allow 2>nul
echo ✅ Optimizations applied
echo.

echo [Step 8/8] Configuring and launching...
adb shell monkey -p %PKG% -c android.intent.category.LAUNCHER 1 >nul 2>nul
timeout /t 2 /nobreak >nul
adb shell am broadcast --receiver-foreground -a %PKG%.CONFIGURE -n %PKG%/.ConfigReceiver --es server_url "%BASE_URL%" --es token "%ADMIN_KEY%" --es alias "%ALIAS%"
if errorlevel 1 (
    echo ❌ Configuration broadcast failed
    exit /b 8
)
timeout /t 3 /nobreak >nul

adb shell pidof %PKG% >nul && (
    echo ✅ Service running
) || (
    echo ⚠ Service not detected yet (may start shortly)
)

echo.
echo ==========================================
echo ✅ ENROLLMENT COMPLETE
echo ==========================================
echo 📱 Device "%ALIAS%" should appear in dashboard within ~60s
echo 📋 Android %DEVICE_VER% (SDK %DEVICE_SDK%)
echo.
echo NOTE: For best results, generate scripts from the
echo       ADB Setup page in your NexMDM dashboard.
echo.

endlocal
exit /b 0
