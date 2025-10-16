"use client"
import { ProtectedLayout } from "@/components/protected-layout"

import { useState, useEffect } from "react"
import { Copy, Check, Terminal } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Header } from "@/components/header"
import { Sidebar } from "@/components/sidebar"
import { SettingsDrawer } from "@/components/settings-drawer"

export default function ADBSetupPage() {
  return (
    <ProtectedLayout>
      <ADBSetupContent />
    </ProtectedLayout>
  )
}

function ADBSetupContent() {
  const [alias, setAlias] = useState("")
  const [script, setScript] = useState("")
  const [copied, setCopied] = useState(false)
  const [loading, setLoading] = useState(false)
  const [isDark, setIsDark] = useState(false)
  const [isSidebarOpen, setIsSidebarOpen] = useState(true)
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)

  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add("dark")
    } else {
      document.documentElement.classList.remove("dark")
    }
  }, [isDark])

  useEffect(() => {
    const isDarkMode = localStorage.getItem('darkMode') === 'true'
    setIsDark(isDarkMode)
  }, [])

  useEffect(() => {
    const sidebarOpen = localStorage.getItem('sidebarOpen')
    if (sidebarOpen !== null) {
      setIsSidebarOpen(sidebarOpen === 'true')
    }
  }, [])

  const generateScript = async () => {
    if (!alias.trim()) {
      alert("Please enter a device alias")
      return
    }

    setLoading(true)
    try {
      const token = localStorage.getItem('access_token')
      const response = await fetch("/v1/adb-script", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`
        },
        body: JSON.stringify({ alias: alias.trim() }),
      })
      
      if (!response.ok) {
        throw new Error("Failed to generate script")
      }
      
      const data = await response.json()
      setScript(data.script)
    } catch (error) {
      alert("Failed to generate script. Please try again.")
      console.error(error)
    } finally {
      setLoading(false)
    }
  }

  const copyToClipboard = () => {
    navigator.clipboard.writeText(script)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleToggleDark = () => {
    const newDarkMode = !isDark
    setIsDark(newDarkMode)
    localStorage.setItem('darkMode', String(newDarkMode))
  }

  const handleToggleSidebar = () => {
    const newState = !isSidebarOpen
    setIsSidebarOpen(newState)
    localStorage.setItem('sidebarOpen', newState.toString())
  }

  return (
    <div className="min-h-screen bg-background">
      <Sidebar isOpen={isSidebarOpen} onToggle={handleToggleSidebar} />
      
      <Header 
        lastUpdated={Date.now()} 
        alertCount={0} 
        isDark={isDark} 
        onToggleDark={handleToggleDark}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onRefresh={() => {}}
        onToggleSidebar={handleToggleSidebar}
      />
      
      <div className={`transition-all duration-300 mx-auto max-w-[1280px] space-y-6 px-6 py-8 pt-20 md:px-8 ${isSidebarOpen ? 'lg:ml-64' : 'lg:ml-16'}`}>
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <Terminal className="h-6 w-6" />
            <h1 className="text-3xl font-bold tracking-tight">ADB Deployment</h1>
          </div>
          <p className="text-muted-foreground">
            Generate a complete ADB script to install, configure, and enroll Android devices automatically.
          </p>
        </div>

        <div className="rounded-lg border bg-card p-6 shadow-sm">
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="alias">Device Alias</Label>
              <Input
                id="alias"
                placeholder="e.g., Warehouse-Phone-01"
                value={alias}
                onChange={(e) => setAlias(e.target.value)}
                onKeyPress={(e) => e.key === "Enter" && generateScript()}
              />
              <p className="text-xs text-muted-foreground">
                Enter a unique name to identify this device in the dashboard
              </p>
            </div>

            <Button onClick={generateScript} disabled={loading || !alias.trim()}>
              {loading ? "Generating..." : "Generate Script"}
            </Button>
          </div>
        </div>

        {script && (
          <div className="rounded-lg border bg-card p-6 shadow-sm">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold">Deployment Script</h2>
              <Button
                variant="outline"
                size="sm"
                onClick={copyToClipboard}
                className="gap-2"
              >
                {copied ? (
                  <>
                    <Check className="h-4 w-4" />
                    Copied!
                  </>
                ) : (
                  <>
                    <Copy className="h-4 w-4" />
                    Copy Script
                  </>
                )}
              </Button>
            </div>
            
            <pre className="overflow-x-auto rounded-md bg-muted p-4 text-xs">
              <code>{script}</code>
            </pre>

            <div className="mt-4 space-y-2 rounded-md border border-amber-500/50 bg-amber-500/10 p-4">
              <h3 className="font-semibold text-amber-700 dark:text-amber-300">Usage Instructions</h3>
              <ol className="list-decimal space-y-1 pl-5 text-sm text-muted-foreground">
                <li>Make sure <code className="rounded bg-muted px-1">nexmdm.apk</code> is at <code className="rounded bg-muted px-1">C:\Users\gordo\OneDrive\Desktop\nexmdm.apk</code></li>
                <li>Connect your <strong>factory-reset</strong> Android device via USB (no accounts added yet!)</li>
                <li>Open Command Prompt (CMD) and copy-paste the <strong>entire one-liner command</strong> above</li>
                <li>Press Enter and watch the output - it will:
                  <ul className="list-disc pl-5 mt-1">
                    <li>Install APK automatically</li>
                    <li>Set Device Owner (check for "Success" message)</li>
                    <li>Configure all permissions and optimizations</li>
                    <li>Enroll device automatically</li>
                    <li>Verify Device Owner status (shows package name if successful)</li>
                  </ul>
                </li>
                <li>Complete the 2 manual steps shown at the end (Full Screen Intents + Usage Access)</li>
              </ol>
            </div>
          </div>
        )}
      </div>

      <SettingsDrawer
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
      />
    </div>
  )
}
