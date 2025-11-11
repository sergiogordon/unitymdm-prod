@echo off
setlocal enabledelayedexpansion

REM ====== CONFIG ======
set PKG=com.nexmdm
set ALIAS=test
set APK_PATH=%TEMP%\nexmdm-latest.apk
set BASE_URL=https://83b071bb-c5cb-4eda-b79c-d276873904c2-00-2ha4ytvejclnm.worf.replit.dev
set DL_URL=%BASE_URL%/v1/apk/download/latest
set BEARER=_sDKZuilFJVWi3NkpQdEjmM07v2-HuGa3teb7bGKMro

echo [NexMDM Deployment - Device: %ALIAS%]
echo.

echo [Step 0] Waiting for device...
adb wait-for-device || (echo ❌ No device found & exit /b 2)

echo [Step 1/7] Downloading latest APK...
echo [DEBUG] URL: %DL_URL%
curl -L -H "Authorization: Bearer %BEARER%" "%DL_URL%" -o "%APK_PATH%" || (echo ❌ Download failed & exit /b 3)
if not exist "%APK_PATH%" (echo ❌ APK missing at %APK_PATH% & exit /b 3)
echo ✅ APK downloaded!
echo.

echo [Step 2/7] Installing APK (safe update w/ fallback)...
adb install -r "%APK_PATH%"
if errorlevel 1 (
  echo [WARN] Update failed — attempting uninstall + clean install...
  adb shell pm uninstall -k --user 0 %PKG% 1>nul 2>nul
  adb install -t -d "%APK_PATH%" || (echo ❌ Clean install failed & exit /b 4)
)
echo ✅ APK installed/updated!
echo.

echo [Step 3/7] Ensuring Device Owner (DO)...
for /f "tokens=2 delims=: " %%A in ('adb shell settings get secure device_provisioned') do set DEVPROV=%%A
for /f "tokens=2 delims=: " %%A in ('adb shell settings get secure user_setup_complete') do set USERSETUP=%%A

REM Trim CR/LF
set DEVPROV=%DEVPROV:~0,1%
set USERSETUP=%USERSETUP:~0,1%

adb shell dumpsys device_policy | findstr /C:"Device Owner" /C:"%PKG%" >nul
if errorlevel 1 (
  echo [INFO] Device Owner not detected for %PKG%.
  if "%DEVPROV%"=="1" if "%USERSETUP%"=="1" (
    echo ❌ Cannot set Device Owner on a provisioned device.
    echo     Device Owner requires a factory-reset / unprovisioned state.
    echo     Please wipe the device (or use QR/NFC provisioning) and re-run.
    exit /b 5
  )
  adb shell dpm set-device-owner %PKG%/.NexDeviceAdminReceiver 1>nul 2>nul || (
    echo ❌ Failed to set Device Owner. Ensure device is factory-fresh and compatible.
    exit /b 6
  )
)

adb shell dumpsys device_policy | findstr /C:"%PKG%" >nul || (
  echo ❌ Device Owner verification failed.
  exit /b 7
)
echo ✅ Device Owner confirmed.
echo.

echo [Step 4/7] Permissions & Doze whitelist...
adb shell pm grant %PKG% android.permission.POST_NOTIFICATIONS 2>nul
adb shell pm grant %PKG% android.permission.CAMERA 2>nul
adb shell pm grant %PKG% android.permission.ACCESS_FINE_LOCATION 2>nul
adb shell appops set %PKG% RUN_ANY_IN_BACKGROUND allow 2>nul
adb shell appops set %PKG% AUTO_REVOKE_PERMISSIONS_IF_UNUSED ignore 2>nul
adb shell appops set %PKG% GET_USAGE_STATS allow 2>nul
adb shell dumpsys deviceidle whitelist +%PKG% 1>nul
echo ✅ Whitelisted ^& permissions set!
echo.

echo [Step 5/7] Applying full optimizations and bloat off...
adb shell "settings put global window_animation_scale 0.5; settings put global transition_animation_scale 0.5; settings put global animator_duration_scale 0.5; settings put global ambient_tilt_to_wake 1; settings put global ambient_touch_to_wake 1; settings put global app_standby_enabled 0; settings put global adaptive_battery_management_enabled 0; settings put global app_restriction_enabled false; settings put global dynamic_power_savings_enabled 0; settings put global battery_tip_constants advertise_disable_apps_enabled=false; settings put secure location_mode 0; settings put global assisted_gps_enabled 0; settings put global wifi_scan_always_enabled 0; settings put global ble_scan_always_enabled 0; settings put global network_recommendations_enabled 0; settings put global wifi_networks_available_notification_on 0; settings put secure install_non_market_apps 1; settings put global stay_on_while_plugged_in 7; settings put global device_provisioned 1; settings put secure user_setup_complete 1; settings put system screen_off_timeout 2147483647; settings put global heads_up_notifications_enabled 0; settings put global development_settings_enabled 1; settings put global adb_enabled 1; settings put global package_verifier_enable 0; settings put global verifier_verify_adb_installs 0; settings put global wifi_sleep_policy 2; settings put global bluetooth_on 0"
adb shell dumpsys deviceidle whitelist +com.unitynetwork.unityapp 1>nul
adb shell appops set com.unitynetwork.unityapp RUN_ANY_IN_BACKGROUND allow 2>nul
echo ✅ Optimizations applied!
echo.

echo [Step 6/7] Launch and configure...
adb shell monkey -p %PKG% -c android.intent.category.LAUNCHER 1 1>nul 2>nul
timeout /t 2 /nobreak >nul
echo [DEBUG] Sending CONFIGURE broadcast (foreground)…
adb shell am broadcast --receiver-foreground -a %PKG%.CONFIGURE -n %PKG%/.ConfigReceiver --es server_url "%BASE_URL%" --es token "%BEARER%" --es alias "%ALIAS%"
if errorlevel 1 (
  echo ❌ CONFIGURE broadcast failed.
  exit /b 8
)
timeout /t 3 /nobreak >nul
echo ✅ Configuration broadcast sent!
echo.

echo [Step 7/7] Verifying service...
adb shell pidof %PKG% 1>nul && (
  echo ✅ Service running
) || (
  echo ❌ Service not running
  exit /b 9
)

echo.
echo ==========================================
echo ✅ ENROLLMENT COMPLETE
echo ==========================================
echo 📱 "%ALIAS%" should appear in the dashboard within ~60s.
echo.

endlocal
exit /b 0
