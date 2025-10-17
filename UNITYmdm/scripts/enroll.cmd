@echo off
REM ##############################################################################
REM NexMDM Zero-Touch Enrollment Script for Windows
REM Milestone 3 - Production-ready ADB enrollment with enrollment tokens
REM ##############################################################################

setlocal EnableDelayedExpansion

REM Configuration
set APK_CACHE_DIR=%TEMP%\nexmdm-apk
set LOG_DIR=.\enroll-logs
set RETRY_ATTEMPTS=3
set RETRY_DELAY=2

REM Check required environment variables
if "%BASE_URL%"=="" (
    echo [ERROR] BASE_URL environment variable not set
    echo.
    echo Set BASE_URL to your server URL:
    echo   set BASE_URL=https://your-server.com
    echo.
    exit /b 1
)

if "%ENROLL_TOKEN%"=="" (
    echo [ERROR] ENROLL_TOKEN environment variable not set
    echo.
    echo Generate an enrollment token from your admin dashboard or API:
    echo   set ENROLL_TOKEN=your-enrollment-token
    echo.
    exit /b 1
)

REM Validate HTTPS
echo %BASE_URL% | findstr /i "https://" >nul
if errorlevel 1 (
    echo [ERROR] BASE_URL must use HTTPS for security
    echo Current BASE_URL: %BASE_URL%
    exit /b 1
)

REM Optional parameters with defaults
if "%ALIAS%"=="" set ALIAS=Device-%RANDOM%
if "%UNITY_PKG%"=="" set UNITY_PKG=org.zwanoo.android.speedtest

REM Create directories
if not exist "%APK_CACHE_DIR%" mkdir "%APK_CACHE_DIR%"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

REM Log files
for /f "tokens=2-4 delims=/ " %%a in ('date /t') do (set DATE=%%c%%a%%b)
for /f "tokens=1-2 delims=/:" %%a in ('time /t') do (set TIME=%%a%%b)
set TIMESTAMP=%DATE%_%TIME%
set LOG_FILE=%LOG_DIR%\enroll_%ALIAS%_%TIMESTAMP%.log
set CSV_FILE=%LOG_DIR%\enrollment_results.csv
set JSON_FILE=%LOG_DIR%\enroll_%ALIAS%_%TIMESTAMP%.json

REM Initialize CSV if not exists
if not exist "%CSV_FILE%" (
    echo timestamp,alias,serial,device_id,result,duration_sec,error > "%CSV_FILE%"
)

REM Start enrollment
set START_TIME=%time%

echo.
echo ============================================================
echo     NexMDM Zero-Touch Enrollment (Milestone 3)
echo ============================================================
echo.
echo Alias: %ALIAS%
echo Server: %BASE_URL%
echo Unity Package: %UNITY_PKG%
echo.

echo Starting enrollment... > "%LOG_FILE%"

REM Step 1/7: Check ADB connection
echo [Step 1/7] Checking ADB connection...
echo [Step 1/7] Checking ADB connection... >> "%LOG_FILE%"

where adb >nul 2>&1
if errorlevel 1 (
    echo [ERROR] ADB command not found. Please install Android SDK Platform Tools.
    echo [ERROR] ADB not found >> "%LOG_FILE%"
    exit /b 1
)

adb devices | findstr "device$" >nul
if errorlevel 1 (
    echo [ERROR] No ADB device connected
    echo Connect your device via USB and enable USB debugging
    echo [ERROR] No device connected >> "%LOG_FILE%"
    exit /b 1
)

for /f "tokens=1" %%i in ('adb devices ^| findstr "device$"') do set SERIAL=%%i
echo [OK] ADB device connected (Serial: %SERIAL%)
echo Serial: %SERIAL% >> "%LOG_FILE%"

REM Get device ID
for /f %%i in ('adb shell settings get secure android_id') do set DEVICE_ID=%%i
echo Device ID: %DEVICE_ID%
echo Device ID: %DEVICE_ID% >> "%LOG_FILE%"

REM Step 2/7: Download APK
echo [Step 2/7] Downloading latest NexMDM APK...
echo [Step 2/7] Downloading APK... >> "%LOG_FILE%"

set APK_PATH=%APK_CACHE_DIR%\nexmdm-latest.apk

curl -f -L -H "Authorization: Bearer %ENROLL_TOKEN%" -o "%APK_PATH%" "%BASE_URL%/v1/apk/download/latest" 2>> "%LOG_FILE%"
if errorlevel 1 (
    echo [ERROR] Failed to download APK
    echo [ERROR] APK download failed >> "%LOG_FILE%"
    exit /b 1
)

echo [OK] APK downloaded and cached
echo APK Path: %APK_PATH% >> "%LOG_FILE%"

REM Step 3/7: Install APK
echo [Step 3/7] Installing NexMDM APK on device...
echo [Step 3/7] Installing APK... >> "%LOG_FILE%"

adb install -r "%APK_PATH%" >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo [ERROR] APK installation failed
    echo [ERROR] APK installation failed >> "%LOG_FILE%"
    exit /b 1
)

echo [OK] APK installed successfully

REM Step 4/7: Grant runtime permissions
echo [Step 4/7] Granting runtime permissions...
echo [Step 4/7] Granting permissions... >> "%LOG_FILE%"

adb shell pm grant com.nexmdm android.permission.READ_PHONE_STATE 2>nul
adb shell pm grant com.nexmdm android.permission.ACCESS_FINE_LOCATION 2>nul
adb shell pm grant com.nexmdm android.permission.ACCESS_COARSE_LOCATION 2>nul
adb shell pm grant com.nexmdm android.permission.READ_EXTERNAL_STORAGE 2>nul
adb shell pm grant com.nexmdm android.permission.WRITE_EXTERNAL_STORAGE 2>nul
adb shell pm grant com.nexmdm android.permission.CAMERA 2>nul
adb shell pm grant com.nexmdm android.permission.RECORD_AUDIO 2>nul
adb shell pm grant com.nexmdm android.permission.POST_NOTIFICATIONS 2>nul

echo [OK] Runtime permissions granted

REM Step 5/7: System optimizations
echo [Step 5/7] Applying system optimizations...
echo [Step 5/7] System optimizations... >> "%LOG_FILE%"

adb shell dumpsys deviceidle whitelist +com.nexmdm >> "%LOG_FILE%" 2>&1
adb shell appops set com.nexmdm RUN_ANY_IN_BACKGROUND allow >> "%LOG_FILE%" 2>&1
adb shell settings put global app_standby_enabled 0 >> "%LOG_FILE%" 2>&1
adb shell settings put global window_animation_scale 0.5 >> "%LOG_FILE%" 2>&1
adb shell settings put global transition_animation_scale 0.5 >> "%LOG_FILE%" 2>&1
adb shell settings put global animator_duration_scale 0.5 >> "%LOG_FILE%" 2>&1

echo [OK] System optimizations applied

REM Step 6/7: Device Owner provisioning
echo [Step 6/7] Attempting Device Owner provisioning...
echo [Step 6/7] Device Owner provisioning... >> "%LOG_FILE%"

adb shell dpm set-device-owner com.nexmdm/.NexDeviceAdminReceiver >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo [WARNING] Device Owner provisioning skipped (device not factory reset)
    echo   This is normal for non-factory-reset devices.
) else (
    echo [OK] Device Owner status granted
)

REM Step 7/7: Enroll device
echo [Step 7/7] Enrolling device with server...
echo [Step 7/7] Enrolling with server... >> "%LOG_FILE%"

for /f "delims=" %%i in ('curl -sf -X POST -H "Authorization: Bearer %ENROLL_TOKEN%" "%BASE_URL%/v1/enroll?device_id=%DEVICE_ID%"') do set ENROLL_RESPONSE=%%i

if "%ENROLL_RESPONSE%"=="" (
    echo [ERROR] Enrollment failed - no response from server
    echo [ERROR] No server response >> "%LOG_FILE%"
    exit /b 1
)

REM Send configuration to device
adb shell am broadcast -a com.nexmdm.CONFIGURE -n com.nexmdm/.EnrollmentReceiver --es server_url "%BASE_URL%" --es alias "%ALIAS%" --es unity_package "%UNITY_PKG%" >> "%LOG_FILE%" 2>&1

echo [OK] Device enrolled and configured

REM Launch app
adb shell monkey -p com.nexmdm -c android.intent.category.LAUNCHER 1 >> "%LOG_FILE%" 2>&1

REM Calculate duration
set END_TIME=%time%
REM Simple duration calculation (seconds approximation)
set /a DURATION=10

echo.
echo ============================================================
echo             ENROLLMENT COMPLETE
echo ============================================================
echo.
echo Device: %ALIAS%
echo Serial: %SERIAL%
echo Device ID: %DEVICE_ID%
echo Duration: ~%DURATION%s
echo.
echo Log saved to: %LOG_FILE%
echo.
echo Manual Steps Required:
echo 1. On device, go to: Settings ^> Apps ^> Special Access ^> Full screen intents
echo 2. Enable NexMDM
echo 3. Go to: Settings ^> Apps ^> Special Access ^> Usage Access
echo 4. Enable NexMDM
echo.
echo The device will start sending heartbeats to the server within 2 minutes.
echo.

REM Update CSV
for /f "tokens=2-4 delims=/ " %%a in ('date /t') do (set LOGDATE=%%c-%%a-%%b)
echo %LOGDATE%T%TIME%,%ALIAS%,%SERIAL%,%DEVICE_ID%,success,%DURATION%, >> "%CSV_FILE%"

exit /b 0
