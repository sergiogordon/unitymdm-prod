"use client"

import { useState, useEffect } from "react"
import { Download, Copy, Check } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Header } from "@/components/header"
import { Sidebar } from "@/components/sidebar"
import { SettingsDrawer } from "@/components/settings-drawer"
import { toast } from "sonner"
import { useTheme } from "@/contexts/ThemeContext"

export default function DemoAdbSetupPage() {
  const { isDark, toggleTheme } = useTheme()
  const [isSidebarOpen, setIsSidebarOpen] = useState(true)
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  const [lastUpdated] = useState(Date.now())
  const [deviceAlias, setDeviceAlias] = useState("Demo Device")
  const [copied, setCopied] = useState(false)
  
  // Static demo script - no API call needed
  const script = `#!/bin/bash
# UNITYmdm Demo ADB Setup Script
# Device Alias: ${deviceAlias}
# This is a demonstration of the automated enrollment process

echo "===================================="
echo "  UNITYmdm Automated Deployment"
echo "===================================="
echo ""
echo "Device Alias: ${deviceAlias}"
echo ""
echo "[Step 1/6] Downloading latest UNITYmdm APK..."
echo "✓ APK downloaded successfully"
echo ""
echo "[Step 2/6] Installing APK via ADB..."
echo "✓ APK installed on device"
echo ""
echo "[Step 3/6] Granting permissions..."
echo "✓ All permissions granted"
echo ""
echo "[Step 4/6] Configuring battery optimization..."
echo "✓ Battery whitelist applied"
echo ""
echo "[Step 5/6] Setting up Device Owner mode..."
echo "✓ Device Owner configured"
echo ""
echo "[Step 6/6] Enrolling device with server..."
echo "✓ Device enrolled successfully!"
echo ""
echo "===================================="
echo "  Demo Mode - Setup Complete!"
echo "===================================="
echo ""
echo "In production, this script automatically:"
echo "  • Downloads the latest APK from your server"
echo "  • Installs it via ADB"
echo "  • Grants all necessary permissions"
echo "  • Disables battery optimization"
echo "  • Sets up Device Owner mode"
echo "  • Enrolls the device automatically"
echo ""
echo "Your device would now appear in the dashboard!"
`


  const handleToggleSidebar = () => {
    setIsSidebarOpen(!isSidebarOpen)
  }

  const handleCopyScript = async () => {
    try {
      await navigator.clipboard.writeText(script)
      setCopied(true)
      toast.success('Script copied to clipboard')
      setTimeout(() => setCopied(false), 2000)
    } catch (error) {
      toast.error('Failed to copy script')
    }
  }

  const handleDownloadScript = () => {
    const blob = new Blob([script], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `nexmdm-demo-setup.sh`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    toast.success('Script downloaded')
  }

  return (
    <div className="min-h-screen">
      <Sidebar isOpen={isSidebarOpen} onToggle={handleToggleSidebar} />
      
      <Header
        lastUpdated={lastUpdated}
        alertCount={0}
        isDark={isDark}
        onToggleDark={toggleTheme}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onRefresh={() => {}}
        onToggleSidebar={handleToggleSidebar}
      />

      <div className={`transition-all duration-300 mx-auto max-w-[1280px] space-y-6 px-6 py-8 pt-20 md:px-8 ${isSidebarOpen ? 'lg:ml-64' : 'lg:ml-16'}`}>
        <div className="space-y-2">
          <h2 className="text-2xl font-semibold tracking-tight">ADB Setup</h2>
          <p className="text-sm text-muted-foreground">Generate automated enrollment scripts for Android devices</p>
        </div>

        <div className="rounded-lg border border-border/40 bg-card p-6 space-y-6">
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="device-alias">Device Alias</Label>
              <Input
                id="device-alias"
                type="text"
                value={deviceAlias}
                onChange={(e) => setDeviceAlias(e.target.value)}
                placeholder="Enter device alias"
              />
              <p className="text-xs text-muted-foreground">
                Change the alias above to see it reflected in the script
              </p>
            </div>
          </div>

          <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-medium">Generated ADB Script</h3>
                <div className="flex items-center gap-2">
                  <Button size="sm" variant="outline" onClick={handleCopyScript}>
                    {copied ? (
                      <>
                        <Check className="h-4 w-4 mr-2" />
                        Copied
                      </>
                    ) : (
                      <>
                        <Copy className="h-4 w-4 mr-2" />
                        Copy
                      </>
                    )}
                  </Button>
                  <Button size="sm" onClick={handleDownloadScript}>
                    <Download className="h-4 w-4 mr-2" />
                    Download
                  </Button>
                </div>
              </div>

              <div className="relative">
                <pre className="rounded-lg bg-muted p-4 text-sm overflow-x-auto max-h-[500px] overflow-y-auto">
                  <code>{script}</code>
                </pre>
              </div>

              <div className="rounded-lg bg-blue-500/10 border border-blue-500/20 p-4">
                <p className="text-sm text-blue-600 dark:text-blue-400">
                  <strong>Demo Mode:</strong> This is a demonstration script. In production, this script would download the latest APK, install it on your device via ADB, grant permissions, and enroll the device automatically.
                </p>
              </div>
            </div>
        </div>

        <div className="rounded-lg border border-border/40 bg-card p-6 space-y-4">
          <h3 className="text-lg font-medium">How to use this script</h3>
          <ol className="list-decimal list-inside space-y-2 text-sm text-muted-foreground">
            <li>Enable USB debugging on your Android device</li>
            <li>Connect your device to your computer via USB</li>
            <li>Download and run the generated script</li>
            <li>The script will automatically install and configure UNITYmdm</li>
            <li>Your device will appear in the dashboard once enrolled</li>
          </ol>
        </div>
      </div>

      <SettingsDrawer 
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
      />
    </div>
  )
}
