@echo off
setlocal enabledelayedexpansion

REM ==============================================================================
REM UnityMDM Batch Enrollment Script v3.0
REM Automatically enrolls all connected Android devices with sequential D# aliases
REM ==============================================================================

set SERVER_URL=https://unitymdm.replit.app
set ADMIN_KEY=ldWh9geFGp2QbdRQQWvzGzwI56hb2FD4GdC48CKjT1Y=
set APK_URL=%SERVER_URL%/download/mdm-agent.apk

echo.
echo ================================================================================
echo UnityMDM Batch Enrollment - Starting
echo ================================================================================
echo.

REM Check if ADB is available
where adb >nul 2>&1
if errorlevel 1 (
    echo [ERROR] ADB not found in PATH
    echo Please install Android Platform Tools and add to PATH
    echo Download from: https://developer.android.com/tools/releases/platform-tools
    pause
    exit /b 1
)

REM Get list of connected devices
echo [1/7] Detecting connected devices...
adb devices > "%TEMP%\adb_devices.txt"

REM Count devices (skip first line which is "List of devices attached")
set DEVICE_COUNT=0
for /f "skip=1 tokens=1" %%D in (%TEMP%\adb_devices.txt) do (
    if not "%%D"=="" (
        set /a DEVICE_COUNT+=1
    )
)

if %DEVICE_COUNT%==0 (
    echo [ERROR] No devices connected via ADB
    echo.
    echo Troubleshooting:
    echo 1. Connect Android device via USB
    echo 2. Enable USB Debugging in Developer Options
    echo 3. Accept USB Debugging prompt on device
    echo 4. Run: adb devices
    pause
    exit /b 1
)

echo Found %DEVICE_COUNT% device(s) connected
echo.

REM Fetch last alias from backend
echo [2/7] Fetching last alias from backend...
curl -s -H "X-Admin-Key: %ADMIN_KEY%" "%SERVER_URL%/admin/devices/last-alias" -o "%TEMP%\last_alias.json"

if errorlevel 1 (
    echo [WARNING] Could not fetch last alias from server, starting from D01
    set NEXT_NUM=1
) else (
    REM Parse JSON to get next_number
    for /f "tokens=2 delims=:, " %%N in ('findstr "next_number" "%TEMP%\last_alias.json"') do (
        set NEXT_NUM=%%N
    )
)

echo Next alias will be: D!NEXT_NUM!
echo.

REM Process each device
echo [3/7] Beginning enrollment for %DEVICE_COUNT% device(s)...
echo.

set CURRENT_NUM=!NEXT_NUM!
set SUCCESS_COUNT=0
set FAIL_COUNT=0

for /f "skip=1 tokens=1" %%D in (%TEMP%\adb_devices.txt) do (
    if not "%%D"=="" (
        set SERIAL=%%D
        
        REM Format alias with zero-padding
        if !CURRENT_NUM! LSS 10 (
            set ALIAS=D0!CURRENT_NUM!
        ) else (
            set ALIAS=D!CURRENT_NUM!
        )
        
        echo ----------------------------------------
        echo Device: !SERIAL!
        echo Alias: !ALIAS!
        echo ----------------------------------------
        
        REM Check if device is already enrolled
        echo [Step 1/9] Checking enrollment status...
        adb -s !SERIAL! shell pm list packages | findstr "com.nexmdm.agent" >nul 2>&1
        if not errorlevel 1 (
            echo [SKIP] Device already has MDM agent installed
            echo.
            goto :next_device
        )
        
        REM Download APK
        echo [Step 2/9] Downloading MDM agent APK...
        curl -# -o "%TEMP%\mdm-agent.apk" "%APK_URL%"
        if errorlevel 1 (
            echo [ERROR] Failed to download APK
            set /a FAIL_COUNT+=1
            goto :next_device
        )
        
        REM Install APK
        echo [Step 3/9] Installing APK...
        adb -s !SERIAL! install -r "%TEMP%\mdm-agent.apk" >nul 2>&1
        if errorlevel 1 (
            echo [ERROR] Failed to install APK
            set /a FAIL_COUNT+=1
            goto :next_device
        )
        
        REM Grant permissions
        echo [Step 4/9] Granting permissions...
        adb -s !SERIAL! shell pm grant com.nexmdm.agent android.permission.READ_PHONE_STATE >nul 2>&1
        adb -s !SERIAL! shell pm grant com.nexmdm.agent android.permission.ACCESS_FINE_LOCATION >nul 2>&1
        adb -s !SERIAL! shell pm grant com.nexmdm.agent android.permission.READ_EXTERNAL_STORAGE >nul 2>&1
        adb -s !SERIAL! shell pm grant com.nexmdm.agent android.permission.WRITE_EXTERNAL_STORAGE >nul 2>&1
        
        REM Set Device Owner
        echo [Step 5/9] Setting Device Owner mode...
        adb -s !SERIAL! shell dpm set-device-owner com.nexmdm.agent/.DeviceAdminReceiver >nul 2>&1
        if errorlevel 1 (
            echo [WARNING] Device Owner mode may have failed - check manually
        )
        
        REM System tweaks
        echo [Step 6/9] Applying system optimizations...
        adb -s !SERIAL! shell settings put global app_standby_enabled 0 >nul 2>&1
        adb -s !SERIAL! shell settings put global app_auto_restriction_enabled false >nul 2>&1
        adb -s !SERIAL! shell dumpsys deviceidle whitelist +com.nexmdm.agent >nul 2>&1
        
        REM Broadcast registration
        echo [Step 7/9] Broadcasting registration intent...
        adb -s !SERIAL! shell am broadcast -a com.nexmdm.agent.ENROLL --es alias "!ALIAS!" --es server_url "%SERVER_URL%" >nul 2>&1
        
        REM Launch app
        echo [Step 8/9] Launching MDM agent...
        adb -s !SERIAL! shell am start -n com.nexmdm.agent/.MainActivity >nul 2>&1
        
        REM Verify enrollment
        echo [Step 9/9] Verifying enrollment...
        timeout /t 3 /nobreak >nul
        
        curl -s -H "X-Admin-Key: %ADMIN_KEY%" "%SERVER_URL%/admin/devices?alias=!ALIAS!" -o "%TEMP%\verify_!ALIAS!.json"
        findstr "!ALIAS!" "%TEMP%\verify_!ALIAS!.json" >nul 2>&1
        if errorlevel 1 (
            echo [WARNING] Device not yet visible in backend (may take 1-2 minutes)
        ) else (
            echo [SUCCESS] Device enrolled as !ALIAS!
        )
        
        set /a SUCCESS_COUNT+=1
        
        :next_device
        set /a CURRENT_NUM+=1
        echo.
    )
)

REM Summary
echo ================================================================================
echo Batch Enrollment Complete
echo ================================================================================
echo Total Devices: %DEVICE_COUNT%
echo Successfully Enrolled: %SUCCESS_COUNT%
echo Failed: %FAIL_COUNT%
echo ================================================================================
echo.
echo Next Steps:
echo 1. Check https://unitymdm.replit.app dashboard for device status
echo 2. Devices should appear within 1-2 minutes
echo 3. Look for aliases: D%NEXT_NUM% through D!CURRENT_NUM!
echo.
pause
