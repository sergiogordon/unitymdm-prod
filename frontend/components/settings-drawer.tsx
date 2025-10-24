"use client"

import { useEffect, useState, useRef } from "react"
import { X, Copy, Check, LogOut } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useRouter } from "next/navigation"
import { logout } from "@/lib/api-client"
import { useToast } from "@/hooks/use-toast"

interface SettingsDrawerProps {
  isOpen: boolean
  onClose: () => void
}

interface MonitoringDefaults {
  enabled: boolean
  package: string
  alias: string
  threshold_min: number
  updated_at: string | null
}

export function SettingsDrawer({ isOpen, onClose }: SettingsDrawerProps) {
  const router = useRouter()
  const { toast } = useToast()
  const [lastTestAlert, setLastTestAlert] = useState<string | null>(null)
  const [copiedItem, setCopiedItem] = useState<string | null>(null)
  
  const [monitoringDefaults, setMonitoringDefaults] = useState<MonitoringDefaults>({
    enabled: true,
    package: "org.zwanoo.android.speedtest",
    alias: "Speedtest",
    threshold_min: 10,
    updated_at: null
  })
  const [monitoringDefaultsOriginal, setMonitoringDefaultsOriginal] = useState<MonitoringDefaults | null>(null)
  const [isSavingMonitoring, setIsSavingMonitoring] = useState(false)
  const [autoSaveStatus, setAutoSaveStatus] = useState<'idle' | 'saving' | 'saved'>('idle')
  const autoSaveTimerRef = useRef<NodeJS.Timeout | null>(null)

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    if (isOpen) {
      document.addEventListener("keydown", handleEscape)
      document.body.style.overflow = "hidden"
      fetchMonitoringDefaults()
    }
    return () => {
      document.removeEventListener("keydown", handleEscape)
      document.body.style.overflow = "unset"
    }
  }, [isOpen, onClose])

  const fetchMonitoringDefaults = async () => {
    try {
      const response = await fetch('/v1/settings/monitoring-defaults', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('jwt_token')}`
        }
      })
      if (response.ok) {
        const data = await response.json()
        setMonitoringDefaults(data)
        setMonitoringDefaultsOriginal(data)
      }
    } catch (error) {
      console.error('Failed to fetch monitoring defaults:', error)
    }
  }

  const handleSaveMonitoringDefaults = async (showToast = true) => {
    setIsSavingMonitoring(true)
    setAutoSaveStatus('saving')
    try {
      const response = await fetch('/v1/settings/monitoring-defaults', {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('jwt_token')}`
        },
        body: JSON.stringify(monitoringDefaults)
      })
      
      if (response.ok) {
        const data = await response.json()
        setMonitoringDefaults(data)
        setMonitoringDefaultsOriginal(data)
        setAutoSaveStatus('saved')
        setTimeout(() => setAutoSaveStatus('idle'), 2000)
        if (showToast) {
          toast({
            title: "Success",
            description: "Monitoring defaults saved successfully"
          })
        }
      } else {
        const error = await response.json()
        setAutoSaveStatus('idle')
        toast({
          title: "Error",
          description: error.detail || "Failed to save monitoring defaults",
          variant: "destructive"
        })
      }
    } catch (error) {
      setAutoSaveStatus('idle')
      toast({
        title: "Error",
        description: "Failed to save monitoring defaults",
        variant: "destructive"
      })
    } finally {
      setIsSavingMonitoring(false)
    }
  }

  const handleCancelMonitoringDefaults = () => {
    if (monitoringDefaultsOriginal) {
      setMonitoringDefaults(monitoringDefaultsOriginal)
    }
  }

  const hasMonitoringChanges = monitoringDefaultsOriginal && (
    monitoringDefaults.enabled !== monitoringDefaultsOriginal.enabled ||
    monitoringDefaults.package !== monitoringDefaultsOriginal.package ||
    monitoringDefaults.alias !== monitoringDefaultsOriginal.alias ||
    monitoringDefaults.threshold_min !== monitoringDefaultsOriginal.threshold_min
  )

  useEffect(() => {
    if (autoSaveTimerRef.current) {
      clearTimeout(autoSaveTimerRef.current)
    }

    if (hasMonitoringChanges) {
      autoSaveTimerRef.current = setTimeout(() => {
        handleSaveMonitoringDefaults(false)
      }, 1500)
    }

    return () => {
      if (autoSaveTimerRef.current) {
        clearTimeout(autoSaveTimerRef.current)
      }
    }
  }, [monitoringDefaults])

  const handleSendTestAlert = () => {
    setLastTestAlert(new Date().toLocaleString())
  }

  const handleCopy = (text: string, item: string) => {
    navigator.clipboard.writeText(text)
    setCopiedItem(item)
    setTimeout(() => setCopiedItem(null), 2000)
  }

  const handleSignOut = () => {
    logout()
    onClose()
    router.push('/login')
  }

  if (!isOpen) return null

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/20 backdrop-blur-sm" onClick={onClose} />
      <div className="fixed right-0 top-0 z-50 h-full w-full max-w-[480px] animate-in slide-in-from-right">
        <div className="flex h-full flex-col bg-card shadow-2xl">
          <div className="flex items-center justify-between border-b border-border px-6 py-4">
            <h2 className="text-lg font-semibold">Settings</h2>
            <Button variant="ghost" size="icon" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          </div>

          <div className="flex-1 overflow-y-auto p-6">
            {/* Monitoring Defaults */}
            <section className="mb-8">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold">Monitoring Defaults</h3>
                {autoSaveStatus === 'saving' && (
                  <span className="text-xs text-muted-foreground">Saving...</span>
                )}
                {autoSaveStatus === 'saved' && (
                  <span className="flex items-center gap-1 text-xs text-green-600">
                    <Check className="h-3 w-3" />
                    Saved
                  </span>
                )}
              </div>
              <p className="mb-4 text-sm text-muted-foreground">
                Configure default monitoring settings for new devices. Changes save automatically.
              </p>
              <div className="space-y-4">
                <div>
                  <label className="mb-2 block text-sm text-muted-foreground">Monitored Package</label>
                  <input
                    type="text"
                    className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
                    placeholder="com.example.app"
                    value={monitoringDefaults.package}
                    onChange={(e) => setMonitoringDefaults({ ...monitoringDefaults, package: e.target.value })}
                  />
                </div>
                <div>
                  <label className="mb-2 block text-sm text-muted-foreground">Display Name (Alias)</label>
                  <input
                    type="text"
                    className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
                    placeholder="App Name"
                    maxLength={64}
                    value={monitoringDefaults.alias}
                    onChange={(e) => setMonitoringDefaults({ ...monitoringDefaults, alias: e.target.value })}
                  />
                </div>
                <div>
                  <label className="mb-2 block text-sm text-muted-foreground">
                    Foreground Timeout (minutes)
                  </label>
                  <input
                    type="number"
                    min={1}
                    max={120}
                    className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
                    value={monitoringDefaults.threshold_min}
                    onChange={(e) => setMonitoringDefaults({ ...monitoringDefaults, threshold_min: parseInt(e.target.value) || 1 })}
                  />
                  <p className="mt-1 text-xs text-muted-foreground">Alert if app hasn't been in foreground for this many minutes</p>
                </div>
                <div className="flex items-center justify-between">
                  <label className="text-sm text-muted-foreground">Enable Monitoring Globally</label>
                  <button
                    className={`relative h-6 w-11 rounded-full transition-colors ${
                      monitoringDefaults.enabled ? 'bg-primary' : 'bg-muted'
                    }`}
                    onClick={() => setMonitoringDefaults({ ...monitoringDefaults, enabled: !monitoringDefaults.enabled })}
                  >
                    <span
                      className={`absolute top-1 h-4 w-4 rounded-full bg-background transition-transform ${
                        monitoringDefaults.enabled ? 'translate-x-6' : 'translate-x-1'
                      }`}
                    />
                  </button>
                </div>
              </div>
              {hasMonitoringChanges && (
                <div className="mt-4 flex gap-2">
                  <Button
                    onClick={() => handleSaveMonitoringDefaults(true)}
                    disabled={isSavingMonitoring}
                    className="flex-1"
                  >
                    {isSavingMonitoring ? "Saving..." : "Save Now"}
                  </Button>
                  <Button
                    variant="outline"
                    onClick={handleCancelMonitoringDefaults}
                    disabled={isSavingMonitoring}
                    className="flex-1"
                  >
                    Discard
                  </Button>
                </div>
              )}
            </section>

            {/* Display Preferences */}
            <section className="mb-8">
              <h3 className="mb-4 text-sm font-semibold">Display Preferences</h3>
              <div className="space-y-4">
                <div>
                  <label className="mb-2 block text-sm text-muted-foreground">Refresh Interval</label>
                  <select className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm">
                    <option>30 seconds</option>
                    <option>1 minute</option>
                    <option>5 minutes</option>
                  </select>
                </div>
                <div className="flex items-center justify-between">
                  <label className="text-sm text-muted-foreground">Compact rows</label>
                  <button className="relative h-6 w-11 rounded-full bg-muted transition-colors hover:bg-muted/80">
                    <span className="absolute left-1 top-1 h-4 w-4 rounded-full bg-background transition-transform" />
                  </button>
                </div>
              </div>
            </section>

            {/* Discord */}
            <section className="mb-8">
              <h3 className="mb-4 text-sm font-semibold">Discord</h3>
              <div className="space-y-3">
                <Button onClick={handleSendTestAlert} className="w-full">
                  Send Test Alert
                </Button>
                {lastTestAlert && <p className="text-xs text-muted-foreground">Last test: {lastTestAlert}</p>}
              </div>
            </section>

            {/* Enrollment */}
            <section className="mb-8">
              <h3 className="mb-4 text-sm font-semibold">Enrollment</h3>
              <p className="mb-4 text-sm text-muted-foreground">
                Use these commands to enroll devices.
              </p>

              <div className="mb-4 space-y-3">
                <Button
                  variant="outline"
                  className="w-full justify-between bg-transparent"
                  onClick={() => handleCopy("curl -s https://example.com/enroll.sh | bash", "single")}
                >
                  <span>Copy single-device command</span>
                  {copiedItem === "single" ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                </Button>

                <Button
                  variant="outline"
                  className="w-full justify-between bg-transparent"
                  onClick={() => handleCopy("# Bulk enrollment template...", "bulk")}
                >
                  <span>Copy bulk template</span>
                  {copiedItem === "bulk" ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                </Button>
              </div>

              <div className="rounded-lg bg-muted p-3">
                <p className="mb-2 text-xs font-medium">SERVER_URL</p>
                <code className="text-xs text-muted-foreground">https://mdm.example.com</code>
              </div>

              <p className="mt-3 text-xs text-muted-foreground">
                Remember to set your ADMIN_KEY environment variable before enrolling devices.
              </p>
            </section>

            {/* Android Permissions */}
            <section className="mb-8">
              <h3 className="mb-4 text-sm font-semibold">Android Permissions</h3>
              <ol className="space-y-2 text-sm text-muted-foreground">
                <li>1. Open Settings → Apps → NexMDM Agent</li>
                <li>2. Enable "Display over other apps"</li>
                <li>3. Enable "Modify system settings"</li>
                <li>4. Grant location permissions</li>
                <li>5. Enable battery optimization exemption</li>
              </ol>
            </section>

            {/* Sign Out */}
            <section>
              <Button 
                variant="destructive" 
                className="w-full justify-center gap-2"
                onClick={handleSignOut}
              >
                <LogOut className="h-4 w-4" />
                Sign Out
              </Button>
            </section>
          </div>
        </div>
      </div>
    </>
  )
}
