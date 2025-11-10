@echo off
setlocal enabledelayedexpansion

REM ==============================================================================
REM UnityMDM Zero-Tap Enrollment v2 - Fixed Bloatware Removal
REM ==============================================================================

echo ============================================
echo UnityMDM Zero-Tap Enrollment v2 - D34
echo ============================================
echo.
echo [Step 0/9] Check prerequisites...
where adb >nul 2>&1 && (echo ✅ ADB found & for /f "tokens=*" %%A in ('adb version 2^>nul ^| findstr Bridge') do @echo %%A) || (echo ❌ ADB not found in PATH & echo Fix: Install Android Platform Tools & echo Download: https://developer.android.com/tools/releases/platform-tools)
echo Listing devices:
adb devices -l
echo.
echo [Step 1/9] Wait for device...
adb wait-for-device >nul 2>&1 && (echo ✅ Device connected) || (echo ❌ No device - Check USB cable & adb devices -l)
echo.
echo [Step 2/9] Download APK...
curl -L -H "X-Admin-Key: ldWh9geFGp2QbdRQQWvzGzwI56hb2FD4GdC48CKjT1Y=" "https://83b071bb-c5cb-4eda-b79c-d276873904c2-00-2ha4ytvejclnm.worf.replit.dev/v1/apk/download-latest" -o "%TEMP%\unitymdm.apk" >nul 2>&1 && (echo ✅ APK downloaded) || (echo ❌ Download failed - Check network)
echo.
echo [Step 3/9] Install APK...
(adb install -r -g "%TEMP%\unitymdm.apk" >nul 2>&1 || (adb uninstall com.nexmdm >nul 2>&1 & adb install -r -g -t "%TEMP%\unitymdm.apk" >nul 2>&1)) && (echo ✅ APK installed) || (echo ❌ Install failed)
echo.
echo [Step 4/9] Set Device Owner...
adb shell dpm set-device-owner com.nexmdm/.NexDeviceAdminReceiver >nul 2>&1 && (echo ✅ Device Owner confirmed) || (echo ❌ Device Owner failed - Factory reset required)
echo.
echo [Step 5/9] Grant permissions...
adb shell pm grant com.nexmdm android.permission.POST_NOTIFICATIONS >nul 2>&1
adb shell pm grant com.nexmdm android.permission.ACCESS_FINE_LOCATION >nul 2>&1
adb shell pm grant com.nexmdm android.permission.CAMERA >nul 2>&1
adb shell appops set com.nexmdm RUN_ANY_IN_BACKGROUND allow >nul 2>&1
adb shell appops set com.nexmdm GET_USAGE_STATS allow >nul 2>&1
adb shell dumpsys deviceidle whitelist +com.nexmdm >nul 2>&1
echo ✅ Permissions granted
echo.
echo [Step 6/9] Disable bloatware...
curl -s -H "X-Admin-Key: ldWh9geFGp2QbdRQQWvzGzwI56hb2FD4GdC48CKjT1Y=" "https://83b071bb-c5cb-4eda-b79c-d276873904c2-00-2ha4ytvejclnm.worf.replit.dev/admin/bloatware-list" -o "%TEMP%\mdm_bloatware.txt"
if errorlevel 1 (
    echo ⚠️  Bloatware list download failed - continuing
) else (
    set BLOAT_COUNT=0
    for /f "delims=" %%P in (%TEMP%\mdm_bloatware.txt) do (
        adb shell pm list packages | findstr "%%P" >nul
        if not errorlevel 1 (
            adb shell pm disable-user --user 0 %%P >nul 2>&1
            if not errorlevel 1 set /a BLOAT_COUNT+=1
        )
    )
    echo ✅ Disabled !BLOAT_COUNT! packages
    del "%TEMP%\mdm_bloatware.txt" >nul 2>&1
)
echo.
echo [Step 7/9] Apply system tweaks...
adb shell settings put global app_standby_enabled 0 >nul 2>&1
adb shell settings put global battery_tip_constants app_restriction_enabled=false >nul 2>&1
adb shell settings put system screen_brightness_mode 0 >nul 2>&1
adb shell settings put system ambient_tilt_to_wake 1 >nul 2>&1
adb shell settings put system ambient_touch_to_wake 1 >nul 2>&1
echo ✅ System tweaks applied
echo.
echo [Step 8/9] Auto-enroll and launch...
adb shell am broadcast -a com.nexmdm.CONFIGURE -n com.nexmdm/.ConfigReceiver --receiver-foreground --es server_url "https://83b071bb-c5cb-4eda-b79c-d276873904c2-00-2ha4ytvejclnm.worf.replit.dev" --es admin_key "ldWh9geFGp2QbdRQQWvzGzwI56hb2FD4GdC48CKjT1Y=" --es alias "D34" >nul 2>&1 && (echo ✅ Auto-enrollment initiated & adb shell monkey -p com.nexmdm -c android.intent.category.LAUNCHER 1 >nul 2>&1) || (echo ❌ Broadcast failed)
echo.
echo [Step 9/9] Verify service...
timeout /t 3 /nobreak >nul
adb shell pidof com.nexmdm >nul 2>&1 && (echo ✅ Service running) || (echo ❌ Service not running & exit /b 8)
echo.
echo Verify registration...
echo Waiting 10 seconds for first heartbeat...
timeout /t 10 /nobreak >nul
echo Checking backend for device "D34"...
set API_FILE=%TEMP%\mdm_verify.txt
curl -s -H "X-Admin-Key: ldWh9geFGp2QbdRQQWvzGzwI56hb2FD4GdC48CKjT1Y=" "https://83b071bb-c5cb-4eda-b79c-d276873904c2-00-2ha4ytvejclnm.worf.replit.dev/admin/devices?alias=D34" -o %API_FILE% 2>nul
findstr /C:"\"alias\":\"D34\"" %API_FILE% >nul 2>&1 && (echo ✅ Device registered! & echo. & echo ============================================ & echo ✅✅✅ ENROLLMENT SUCCESS ✅✅✅ & echo ============================================ & echo Device: D34 enrolled and verified! & echo Check dashboard - device should be online & echo ============================================) || (echo ❌ Device NOT found in backend & type %API_FILE% & del %API_FILE% >nul 2>&1 & echo. & echo ============================================ & echo ❌❌❌ ENROLLMENT FAILED ❌❌❌ & echo ============================================ & echo Device: D34 did not register & echo Check server logs & echo ============================================ & exit /b 9)
del %API_FILE% >nul 2>&1
echo.
echo Window will stay open - Type 'exit' to close
pause
