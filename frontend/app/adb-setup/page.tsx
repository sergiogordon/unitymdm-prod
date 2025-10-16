"use client"

import { useState, useEffect } from "react"
import { Header } from "@/components/header"
import { PageHeader } from "@/components/page-header"
import { SettingsDrawer } from "@/components/settings-drawer"
import { Terminal, Copy, Check } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card } from "@/components/ui/card"
import { Label } from "@/components/ui/label"

export default function AdbSetupPage() {
  const [isDark, setIsDark] = useState(false)
  const [lastUpdated, setLastUpdated] = useState(Date.now())
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  const [deviceAlias, setDeviceAlias] = useState("D01")
  const [scriptGenerated, setScriptGenerated] = useState(false)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add("dark")
    } else {
      document.documentElement.classList.remove("dark")
    }
  }, [isDark])

  const handleRefresh = () => {
    setLastUpdated(Date.now())
  }

  const handleGenerateScript = () => {
    setScriptGenerated(true)
  }

  const handleCopyScript = () => {
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const deploymentScript = `#!/bin/bash
# NexMDM Demo ADB Setup Script
# Generated for demonstration purposes only
# Device Alias: ${deviceAlias}

echo "===================================="
echo "  NexMDM Demo Enrollment Script"
echo "===================================="
echo ""
echo "Device Alias: ${deviceAlias}"
echo "Demo Mode: Active"
echo ""
echo "This is a DEMO script for demonstration purposes."
echo "In a real deployment, this script would:"
echo ""
echo "  1. Check if ADB is connected (adb devices)"
echo "  2. Download the latest NexMDM Android APK"
echo "  3. Install it on the connected device (adb install)"
echo "  4. Grant necessary permissions (adb shell pm grant...)"
echo "  5. Configure battery optimization exemptions"
echo "  6. Disable carrier bloatware (optional)"
echo "  7. Set up Device Owner mode (if requested)"
echo "  8. Enroll the device with your server"
echo ""
echo "===================================="
echo "Demo Mode - No actual changes made"
echo "===================================="`

  return (
    <div className="min-h-screen">
      <Header
        lastUpdated={lastUpdated}
        alertCount={0}
        isDark={isDark}
        onToggleDark={() => setIsDark(!isDark)}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onRefresh={handleRefresh}
      />

      <main className="mx-auto max-w-[1280px] px-6 pb-12 pt-[84px] md:px-8">
        <PageHeader
          icon={<Terminal className="h-8 w-8" />}
          title="ADB Deployment"
          description="Generate a complete ADB script to install, configure, and enroll Android devices automatically."
        />

        <div className="space-y-6">
          {/* Device Alias Input */}
          <Card className="rounded-2xl border border-border bg-card p-6 shadow-sm">
            <div className="space-y-4">
              <div>
                <Label htmlFor="device-alias" className="text-sm font-medium text-card-foreground">
                  Device Alias
                </Label>
                <Input
                  id="device-alias"
                  value={deviceAlias}
                  onChange={(e) => setDeviceAlias(e.target.value)}
                  placeholder="D01"
                  className="mt-2 max-w-md"
                />
                <p className="mt-2 text-sm text-muted-foreground">
                  Enter a unique name to identify this device in the dashboard
                </p>
              </div>

              <Button onClick={handleGenerateScript} className="gap-2">
                <Terminal className="h-4 w-4" />
                Generate Script
              </Button>
            </div>
          </Card>

          {/* Deployment Script */}
          {scriptGenerated && (
            <Card className="rounded-2xl border border-border bg-card p-6 shadow-sm">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-lg font-semibold text-card-foreground">Deployment Script</h2>
                <Button variant="outline" size="sm" onClick={handleCopyScript} className="gap-2 bg-transparent">
                  {copied ? (
                    <>
                      <Check className="h-4 w-4" />
                      Copied
                    </>
                  ) : (
                    <>
                      <Copy className="h-4 w-4" />
                      Copy Script
                    </>
                  )}
                </Button>
              </div>

              <div className="overflow-hidden rounded-lg border border-border bg-muted/30">
                <pre className="overflow-x-auto p-4 font-mono text-xs leading-relaxed text-card-foreground">
                  {deploymentScript}
                </pre>
              </div>
            </Card>
          )}
        </div>
      </main>

      <SettingsDrawer isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} />
    </div>
  )
}
