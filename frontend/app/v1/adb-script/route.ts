import { NextRequest, NextResponse } from 'next/server'
import { isDemoRequest, handleDemoRequest } from '@/lib/apiDemoHelper'
import { getBackendUrl } from '@/lib/backend-url'

export async function POST(request: NextRequest) {
  try {
    // Resolve backend URL dynamically on each request
    const BACKEND_URL = getBackendUrl('/v1/adb-script')
    
    // Check if this is a demo mode request
    if (isDemoRequest(request)) {
      return handleDemoRequest(request, '/v1/adb-script', 'POST')
    }

    const body = await request.json()
    const { alias } = body
    
    if (!alias || typeof alias !== 'string' || !alias.trim()) {
      return NextResponse.json({ detail: 'Valid alias is required' }, { status: 400 })
    }

    const authHeader = request.headers.get('Authorization')
    if (!authHeader) {
      return NextResponse.json({ detail: 'Authorization required' }, { status: 401 })
    }

    const configResponse = await fetch(`${BACKEND_URL}/v1/enrollment-qr-payload?alias=${encodeURIComponent(alias)}`, {
      headers: {
        'Content-Type': 'application/json',
      },
    })
    
    if (!configResponse.ok) {
      return NextResponse.json({ detail: 'Failed to fetch configuration' }, { status: 500 })
    }
    
    const data = await configResponse.json()
    const serverUrl = data.server_url || process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'
    const adminKey = data.admin_key

    const whitelistResponse = await fetch(`${BACKEND_URL}/v1/battery-whitelist`, {
      headers: {
        'Authorization': authHeader,
        'Content-Type': 'application/json',
      },
    })
    
    let batteryWhitelistCommands = ''
    if (whitelistResponse.ok) {
      const whitelist = await whitelistResponse.json()
      const enabledPackages = whitelist.filter((entry: any) => entry.enabled).map((entry: any) => entry.package_name)
      
      if (enabledPackages.length > 0) {
        batteryWhitelistCommands = enabledPackages.map((pkg: string) => 
          `adb shell dumpsys deviceidle whitelist +${pkg} && adb shell appops set ${pkg} RUN_ANY_IN_BACKGROUND allow`
        ).join(' && ')
        batteryWhitelistCommands = ' && ' + batteryWhitelistCommands
      }
    }
    
    const sanitizedAlias = alias.trim()
      .replace(/[\u0000-\u001F\u007F\u2028\u2029]/g, '_')
      .replace(/['"\\`$#;|&<>(){}[\]!*?~%^]/g, '_')
    
    const script = `echo [NexMDM Deployment - Device: ${sanitizedAlias}] && echo. && echo [Step 1/6] Downloading latest APK... && curl -H "X-Admin-Key: ${adminKey}" "${serverUrl}/v1/apk/download-latest" -o "%TEMP%\\nexmdm-latest.apk" && echo ✅ APK downloaded! && echo. && echo [Step 2/6] Installing APK... && adb install -r "%TEMP%\\nexmdm-latest.apk" && echo ✅ APK installed! && echo. && echo [Step 3/6] Setting Device Owner (factory-reset devices only)... && adb shell dpm set-device-owner com.nexmdm/.NexDeviceAdminReceiver && echo ✅ Device Owner set! && echo. && echo [Step 4/6] Granting permissions... && adb shell pm grant com.nexmdm android.permission.POST_NOTIFICATIONS && adb shell pm grant com.nexmdm android.permission.CAMERA && adb shell pm grant com.nexmdm android.permission.ACCESS_FINE_LOCATION && adb shell dumpsys deviceidle whitelist +com.nexmdm && adb shell appops set com.nexmdm RUN_ANY_IN_BACKGROUND allow && adb shell appops set com.nexmdm AUTO_REVOKE_PERMISSIONS_IF_UNUSED ignore && adb shell appops set com.nexmdm GET_USAGE_STATS allow && echo ✅ Permissions granted! && echo. && echo [Step 5/6] Applying optimizations and battery whitelist... && adb shell "settings put global window_animation_scale 0.5; settings put global transition_animation_scale 0.5; settings put global animator_duration_scale 0.5; settings put global ambient_tilt_to_wake 1; settings put global ambient_touch_to_wake 1; settings put global app_standby_enabled 0; settings put global adaptive_battery_management_enabled 0; settings put global app_restriction_enabled false; settings put global dynamic_power_savings_enabled 0; settings put global battery_tip_constants app_restriction_enabled=false; pm disable-user --user 0 com.vzw.hss.myverizon; pm disable-user --user 0 com.vzw.apnlib; pm disable-user --user 0 com.verizon.mips.services; pm disable-user --user 0 com.vcast.mediamanager; pm disable-user --user 0 com.reliancecommunications.vvmclient; pm disable-user --user 0 com.google.android.apps.youtube.music; pm disable-user --user 0 com.google.android.youtube; pm disable-user --user 0 com.king.candycrushsaga; pm disable-user --user 0 com.king.candycrushsodasaga; pm disable-user --user 0 com.superplaystudios.dicedreams; pm disable-user --user 0 net.peakgames.toonblast; pm disable-user --user 0 com.staplegames.dice; pm disable-user --user 0 in.playsimple.tripcross; pm disable-user --user 0 com.easybrain.hidden.spots; pm disable-user --user 0 com.easybrain.sudoku.android; pm disable-user --user 0 com.easybrain.art.puzzle; pm disable-user --user 0 net.peakgames.amy; pm disable-user --user 0 air.com.buffalo_studios.newflashbingo; pm disable-user --user 0 com.tripledot.woodoku; pm disable-user --user 0 com.colorwood.jam; pm disable-user --user 0 com.cardgame.spades.free; pm disable-user --user 0 com.soulcompany.bubbleshooter.relaxing; pm enable com.verizon.dmclientupdate; pm enable com.verizon.obdm; pm enable com.verizon.obdm_permissions; settings put global install_non_market_apps 1"${batteryWhitelistCommands} && echo ✅ Optimizations applied! && echo. && echo [Step 6/6] Enrolling device with server... && adb shell am broadcast -a com.nexmdm.ENROLL -n com.nexmdm/.EnrollmentReceiver --es server_url "${serverUrl}" --es device_alias "${sanitizedAlias}" --es admin_key "${adminKey}" && echo. && echo ✅ Enrollment complete! && echo. && echo [Final Steps - Manual on Device] && echo 1. Open Settings -^> Apps -^> Special Access -^> Full screen intents && echo 2. Enable "NexMDM" && echo 3. Open Settings -^> Apps -^> Special Access -^> Usage Access && echo 4. Enable "NexMDM" && echo. && echo [Setup Complete]`
    
    return NextResponse.json({ script })
  } catch (error) {
    console.error('Error generating ADB script:', error)
    return NextResponse.json({ detail: 'Failed to generate script' }, { status: 500 })
  }
}
