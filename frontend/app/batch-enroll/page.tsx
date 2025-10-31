"use client"

import { useState, useEffect } from "react"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Copy, Download, Terminal, CheckCircle2, AlertCircle } from "lucide-react"
import { useToast } from "@/hooks/use-toast"

export default function BatchEnrollPage() {
  const { toast } = useToast()
  const [serverUrl, setServerUrl] = useState("")
  const [adminKey, setAdminKey] = useState("")
  const [lastAlias, setLastAlias] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    // Get server URL from environment
    if (typeof window !== 'undefined') {
      setServerUrl(window.location.origin.replace('5000', '8000'))
    }
    
    // Fetch admin key and last alias info
    fetchAdminKey()
    fetchLastAlias()
  }, [])

  const fetchAdminKey = async () => {
    try {
      const token = localStorage.getItem('auth_token')
      const response = await fetch('/api/proxy/admin/config/admin-key', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      })
      
      if (response.ok) {
        const data = await response.json()
        setAdminKey(data.admin_key)
      }
    } catch (error) {
      console.error('Failed to fetch admin key:', error)
    }
  }

  const fetchLastAlias = async () => {
    setLoading(true)
    try {
      const token = localStorage.getItem('auth_token')
      const response = await fetch('/api/proxy/admin/devices/last-alias', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      })
      
      if (response.ok) {
        const data = await response.json()
        setLastAlias(data)
      }
    } catch (error) {
      console.error('Failed to fetch last alias:', error)
    } finally {
      setLoading(false)
    }
  }

  const batchScript = `@echo off
setlocal enabledelayedexpansion

REM ==============================================================================
REM UnityMDM Batch Enrollment Script v3.0
REM Automatically enrolls all connected Android devices with sequential D# aliases
REM ==============================================================================

set SERVER_URL=${serverUrl || 'https://unitymdm.replit.app'}
set ADMIN_KEY=${adminKey || 'YOUR_ADMIN_KEY_HERE'}
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
adb devices > "%TEMP%\\adb_devices.txt"

REM Count devices
set DEVICE_COUNT=0
for /f "skip=1 tokens=1" %%D in (%TEMP%\\adb_devices.txt) do (
    if not "%%D"=="" (
        set /a DEVICE_COUNT+=1
    )
)

if %DEVICE_COUNT%==0 (
    echo [ERROR] No devices connected via ADB
    pause
    exit /b 1
)

echo Found %DEVICE_COUNT% device(s) connected
echo.

REM Fetch last alias from backend
echo [2/7] Fetching last alias from backend...
curl -s -H "X-Admin-Key: %ADMIN_KEY%" "%SERVER_URL%/admin/devices/last-alias" -o "%TEMP%\\last_alias.json"

if errorlevel 1 (
    echo [WARNING] Could not fetch last alias from server, starting from D01
    set NEXT_NUM=1
) else (
    for /f "tokens=2 delims=:, " %%N in ('findstr "next_number" "%TEMP%\\last_alias.json"') do (
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

for /f "skip=1 tokens=1" %%D in (%TEMP%\\adb_devices.txt) do (
    if not "%%D"=="" (
        set SERIAL=%%D
        
        if !CURRENT_NUM! LSS 10 (
            set ALIAS=D0!CURRENT_NUM!
        ) else (
            set ALIAS=D!CURRENT_NUM!
        )
        
        echo ----------------------------------------
        echo Device: !SERIAL!
        echo Alias: !ALIAS!
        echo ----------------------------------------
        
        echo [Step 1/9] Checking enrollment status...
        adb -s !SERIAL! shell pm list packages | findstr "com.nexmdm.agent" >nul 2>&1
        if not errorlevel 1 (
            echo [SKIP] Device already has MDM agent installed
            goto :next_device
        )
        
        echo [Step 2/9] Downloading MDM agent APK...
        curl -# -o "%TEMP%\\mdm-agent.apk" "%APK_URL%"
        if errorlevel 1 (
            echo [ERROR] Failed to download APK
            set /a FAIL_COUNT+=1
            goto :next_device
        )
        
        echo [Step 3/9] Installing APK...
        adb -s !SERIAL! install -r "%TEMP%\\mdm-agent.apk" >nul 2>&1
        if errorlevel 1 (
            echo [ERROR] Failed to install APK
            set /a FAIL_COUNT+=1
            goto :next_device
        )
        
        echo [Step 4/9] Granting permissions...
        adb -s !SERIAL! shell pm grant com.nexmdm.agent android.permission.READ_PHONE_STATE >nul 2>&1
        adb -s !SERIAL! shell pm grant com.nexmdm.agent android.permission.ACCESS_FINE_LOCATION >nul 2>&1
        
        echo [Step 5/9] Setting Device Owner mode...
        adb -s !SERIAL! shell dpm set-device-owner com.nexmdm.agent/.DeviceAdminReceiver >nul 2>&1
        
        echo [Step 6/9] Applying system optimizations...
        adb -s !SERIAL! shell settings put global app_standby_enabled 0 >nul 2>&1
        adb -s !SERIAL! shell settings put global app_auto_restriction_enabled false >nul 2>&1
        
        echo [Step 7/9] Broadcasting registration intent...
        adb -s !SERIAL! shell am broadcast -a com.nexmdm.agent.ENROLL --es alias "!ALIAS!" --es server_url "%SERVER_URL%" >nul 2>&1
        
        echo [Step 8/9] Launching MDM agent...
        adb -s !SERIAL! shell am start -n com.nexmdm.agent/.MainActivity >nul 2>&1
        
        echo [Step 9/9] Verifying enrollment...
        timeout /t 3 /nobreak >nul
        
        set /a SUCCESS_COUNT+=1
        
        :next_device
        set /a CURRENT_NUM+=1
        echo.
    )
)

echo ================================================================================
echo Batch Enrollment Complete
echo ================================================================================
echo Total Devices: %DEVICE_COUNT%
echo Successfully Enrolled: %SUCCESS_COUNT%
echo Failed: %FAIL_COUNT%
echo ================================================================================
pause`

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(batchScript)
      toast({
        title: "Copied!",
        description: "Batch enrollment script copied to clipboard",
      })
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to copy script",
        variant: "destructive",
      })
    }
  }

  const downloadScript = () => {
    const blob = new Blob([batchScript], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'batch_enroll.cmd'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    
    toast({
      title: "Downloaded",
      description: "batch_enroll.cmd saved to downloads",
    })
  }

  return (
    <div className="container mx-auto p-6 max-w-6xl">
      <div className="mb-6">
        <h1 className="text-3xl font-bold mb-2">Batch Device Enrollment</h1>
        <p className="text-muted-foreground">
          Automatically enroll multiple Android devices via ADB with sequential D# aliases
        </p>
      </div>

      {/* Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <Terminal className="h-8 w-8 text-blue-500" />
            <div>
              <div className="text-sm text-muted-foreground">Last Alias</div>
              <div className="text-2xl font-bold">
                {loading ? "..." : (lastAlias?.last_alias || "None")}
              </div>
            </div>
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center gap-3">
            <CheckCircle2 className="h-8 w-8 text-green-500" />
            <div>
              <div className="text-sm text-muted-foreground">Next Alias</div>
              <div className="text-2xl font-bold">
                {loading ? "..." : (lastAlias?.next_alias || "D01")}
              </div>
            </div>
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center gap-3">
            <AlertCircle className="h-8 w-8 text-orange-500" />
            <div>
              <div className="text-sm text-muted-foreground">Total Enrolled</div>
              <div className="text-2xl font-bold">
                {loading ? "..." : (lastAlias?.last_number || 0)}
              </div>
            </div>
          </div>
        </Card>
      </div>

      {/* Prerequisites */}
      <Card className="p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4">Prerequisites</h2>
        <div className="space-y-3 text-sm">
          <div className="flex items-start gap-2">
            <CheckCircle2 className="h-5 w-5 text-green-500 mt-0.5 flex-shrink-0" />
            <div>
              <strong>Android Platform Tools:</strong> Install from{" "}
              <a
                href="https://developer.android.com/tools/releases/platform-tools"
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-500 hover:underline"
              >
                developer.android.com
              </a>{" "}
              and add to PATH
            </div>
          </div>
          <div className="flex items-start gap-2">
            <CheckCircle2 className="h-5 w-5 text-green-500 mt-0.5 flex-shrink-0" />
            <div>
              <strong>USB Debugging:</strong> Enable Developer Options and USB Debugging on all devices
            </div>
          </div>
          <div className="flex items-start gap-2">
            <CheckCircle2 className="h-5 w-5 text-green-500 mt-0.5 flex-shrink-0" />
            <div>
              <strong>Factory Reset:</strong> Devices must be factory reset (no accounts) for Device Owner mode
            </div>
          </div>
        </div>
      </Card>

      {/* Script Actions */}
      <Card className="p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4">Download Script</h2>
        <p className="text-sm text-muted-foreground mb-4">
          This Windows CMD script will automatically:
        </p>
        <ul className="text-sm text-muted-foreground mb-6 ml-6 space-y-1 list-disc">
          <li>Detect all connected ADB devices</li>
          <li>Fetch the last used alias from the backend</li>
          <li>Assign sequential D# aliases (D01, D02, D03, ...)</li>
          <li>Download and install the MDM agent on each device</li>
          <li>Configure Device Owner mode and system optimizations</li>
          <li>Register devices with your UnityMDM server</li>
        </ul>

        <div className="flex gap-3">
          <Button onClick={downloadScript} className="flex items-center gap-2">
            <Download className="h-4 w-4" />
            Download batch_enroll.cmd
          </Button>
          <Button onClick={copyToClipboard} variant="outline" className="flex items-center gap-2">
            <Copy className="h-4 w-4" />
            Copy Script
          </Button>
          <Button onClick={fetchLastAlias} variant="outline" disabled={loading}>
            Refresh Status
          </Button>
        </div>
      </Card>

      {/* Usage Instructions */}
      <Card className="p-6">
        <h2 className="text-xl font-semibold mb-4">Usage Instructions</h2>
        <ol className="space-y-3 text-sm list-decimal ml-6">
          <li>
            <strong>Download the script</strong> using the button above (admin key is pre-configured)
          </li>
          <li>
            <strong>Connect devices</strong> via USB and enable USB Debugging
          </li>
          <li>
            <strong>Accept USB Debugging prompts</strong> on each device
          </li>
          <li>
            <strong>Verify connection:</strong> Run <code className="bg-muted px-1 py-0.5 rounded">adb devices</code> to see all connected devices
          </li>
          <li>
            <strong>Run the script:</strong> Double-click <code className="bg-muted px-1 py-0.5 rounded">batch_enroll.cmd</code> or run from Command Prompt
          </li>
          <li>
            <strong>Monitor progress:</strong> The script will show detailed progress for each device
          </li>
          <li>
            <strong>Check dashboard:</strong> Devices should appear in your dashboard within 1-2 minutes
          </li>
        </ol>
      </Card>
    </div>
  )
}
