"use client"
import { ProtectedLayout } from "@/components/protected-layout"
import { useState, useEffect } from "react"
import { Copy, Check, Terminal, Download, Command } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Header } from "@/components/header"
import { SettingsDrawer } from "@/components/settings-drawer"
import { useTheme } from "@/contexts/ThemeContext"

export default function ADBSetupPage() {
  return (
    <ProtectedLayout>
      <ADBSetupContent />
    </ProtectedLayout>
  )
}

function ADBSetupContent() {
  const [alias, setAlias] = useState("")
  const { isDark, toggleTheme } = useTheme()
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  const [copiedButton, setCopiedButton] = useState<string | null>(null)

  const copyOneLiner = async (platform: 'windows' | 'bash') => {
    if (!alias.trim()) {
      alert("Please enter a device alias")
      return
    }

    const authToken = localStorage.getItem('auth_token')
    
    const endpoint = platform === 'windows' 
      ? `/api/proxy/v1/scripts/enroll.one-liner.cmd`
      : `/api/proxy/v1/scripts/enroll.one-liner.sh`
    
    const url = `${endpoint}?alias=${encodeURIComponent(alias.trim())}&agent_pkg=com.nexmdm&unity_pkg=org.zwanoo.android.speedtest`
    
    try {
      const response = await fetch(url, {
        headers: {
          "Authorization": `Bearer ${authToken}`
        }
      })
      
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(errorText || "Failed to fetch one-liner")
      }
      
      const oneLinerCommand = await response.text()
      await navigator.clipboard.writeText(oneLinerCommand)
      
      const buttonId = `${platform}-oneliner`
      setCopiedButton(buttonId)
      setTimeout(() => setCopiedButton(null), 2000)
      
      const message = platform === 'windows'
        ? `✅ Windows one-liner copied to clipboard!\n\nPaste into Command Prompt (cmd.exe) to enroll device "${alias.trim()}"`
        : `✅ Bash one-liner copied to clipboard!\n\nPaste into Terminal (Linux/Mac) to enroll device "${alias.trim()}"`
      
      alert(message)
    } catch (error) {
      alert(`Failed to copy ${platform} one-liner. Please try again.`)
      console.error(error)
    }
  }


  return (
    <div className="flex flex-col min-h-screen">
      <Header onToggleDark={toggleTheme} onOpenSettings={() => setIsSettingsOpen(true)} />
      <SettingsDrawer isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} />
      
      <div className="flex-1 p-8 space-y-8 max-w-5xl mx-auto w-full">
        <div>
          <h1 className="text-3xl font-bold mb-2">ADB Setup & Device Enrollment</h1>
          <p className="text-muted-foreground">
            Generate enrollment scripts for Android devices using ADB (Android Debug Bridge)
          </p>
        </div>

        {/* Device Alias Input */}
        <div className="bg-card rounded-lg border border-border p-6 space-y-4">
          <div>
            <h2 className="text-xl font-semibold mb-4">Device Information</h2>
            <div className="space-y-2">
              <Label htmlFor="alias">Device Alias</Label>
              <Input
                id="alias"
                placeholder="e.g., device-001, lobby-tablet, etc."
                value={alias}
                onChange={(e) => setAlias(e.target.value)}
                className="max-w-md"
              />
              <p className="text-sm text-muted-foreground">
                Enter a unique identifier for this device
              </p>
            </div>
          </div>
        </div>

        {/* One-Liner Commands */}
        <div className="bg-card rounded-lg border border-border p-6 space-y-4">
          <div>
            <h2 className="text-xl font-semibold mb-2 flex items-center gap-2">
              <Command className="h-5 w-5" />
              One-Liner Commands
            </h2>
            <p className="text-sm text-muted-foreground mb-4">
              Copy and paste these commands directly into your terminal. The console window will stay open so you can see the results.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Windows (Command Prompt)</Label>
              <Button
                onClick={() => copyOneLiner('windows')}
                className="w-full"
                variant="outline"
                disabled={!alias.trim()}
              >
                {copiedButton === 'windows-oneliner' ? (
                  <>
                    <Check className="h-4 w-4 mr-2" />
                    Copied!
                  </>
                ) : (
                  <>
                    <Copy className="h-4 w-4 mr-2" />
                    Win
                  </>
                )}
              </Button>
            </div>

            <div className="space-y-2">
              <Label>Linux / macOS (Bash)</Label>
              <Button
                onClick={() => copyOneLiner('bash')}
                className="w-full"
                variant="outline"
                disabled={!alias.trim()}
              >
                {copiedButton === 'bash-oneliner' ? (
                  <>
                    <Check className="h-4 w-4 mr-2" />
                    Copied!
                  </>
                ) : (
                  <>
                    <Copy className="h-4 w-4 mr-2" />
                    Bash
                  </>
                )}
              </Button>
            </div>
          </div>
        </div>

        {/* Instructions */}
        <div className="bg-card rounded-lg border border-border p-6 space-y-4">
          <div>
            <h2 className="text-xl font-semibold mb-2 flex items-center gap-2">
              <Terminal className="h-5 w-5" />
              Usage Instructions
            </h2>
          </div>

          <div className="space-y-4 text-sm">
            <div>
              <h3 className="font-semibold mb-2">Prerequisites</h3>
              <ul className="list-disc list-inside space-y-1 text-muted-foreground ml-4">
                <li>ADB (Android Debug Bridge) installed on your computer</li>
                <li>USB cable to connect Android device</li>
                <li>Factory-reset Android device with USB debugging enabled</li>
              </ul>
            </div>

            <div>
              <h3 className="font-semibold mb-2">Steps</h3>
              <ol className="list-decimal list-inside space-y-2 text-muted-foreground ml-4">
                <li>Connect the factory-reset Android device via USB</li>
                <li>Copy the one-liner command for your platform (Windows or Bash)</li>
                <li>Paste the command into your terminal and press Enter</li>
                <li>The script will automatically:
                  <ul className="list-disc list-inside ml-6 mt-1">
                    <li>Download the latest MDM agent APK</li>
                    <li>Install it on the device</li>
                    <li>Set up Device Owner mode</li>
                    <li>Configure the device and auto-enroll it</li>
                  </ul>
                </li>
                <li>Check the dashboard within 60 seconds to see your newly enrolled device</li>
              </ol>
            </div>

            <div className="bg-amber-500/10 border border-amber-500/20 rounded-md p-4">
              <p className="font-semibold text-amber-600 dark:text-amber-400 mb-1">⚠️ Important</p>
              <p className="text-muted-foreground">
                Device Owner mode requires a factory-reset device. If the script fails at the "Set Device Owner" step, 
                you must factory reset the device and try again.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
