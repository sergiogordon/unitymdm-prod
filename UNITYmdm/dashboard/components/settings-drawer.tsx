"use client"

import { useEffect, useState } from "react"
import { X, Copy, Check, QrCode, LogOut, User, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { QRCodeSVG } from "qrcode.react"
import { useAuth } from "@/lib/auth"
import { toast } from "sonner"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"

interface SettingsDrawerProps {
  isOpen: boolean
  onClose: () => void
}

export function SettingsDrawer({ isOpen, onClose }: SettingsDrawerProps) {
  const { user, logout } = useAuth()
  const [lastTestAlert, setLastTestAlert] = useState<string | null>(null)
  const [copiedItem, setCopiedItem] = useState<string | null>(null)
  const [isSendingAlert, setIsSendingAlert] = useState(false)
  const [alertError, setAlertError] = useState<string | null>(null)
  const [qrAlias, setQrAlias] = useState("")
  const [showQrCode, setShowQrCode] = useState(false)
  const [qrPayload, setQrPayload] = useState<string | null>(null)
  const [qrError, setQrError] = useState<string | null>(null)
  const [showInstallQR, setShowInstallQR] = useState(false)
  const [installUrl, setInstallUrl] = useState("")
  const [autoRelaunchEnabled, setAutoRelaunchEnabled] = useState(false)
  const [isUpdatingAutoRelaunch, setIsUpdatingAutoRelaunch] = useState(false)
  const [showAutoRelaunchDialog, setShowAutoRelaunchDialog] = useState(false)
  const [pendingAutoRelaunchValue, setPendingAutoRelaunchValue] = useState(false)
  const [justUpdated, setJustUpdated] = useState(false)

  useEffect(() => {
    if (typeof window !== "undefined") {
      setInstallUrl(`${window.location.origin}/download/nexmdm.apk`)
    }
  }, [])

  useEffect(() => {
    const fetchAutoRelaunchStatus = async () => {
      if (!isOpen || justUpdated) return
      
      try {
        const response = await fetch("/v1/devices?page=1&limit=1")
        if (!response.ok) return
        
        const data = await response.json()
        if (data.devices && data.devices.length > 0) {
          setAutoRelaunchEnabled(data.devices[0].auto_relaunch_enabled || false)
        }
      } catch (error) {
        console.error("Failed to fetch auto-relaunch status:", error)
      }
    }
    
    fetchAutoRelaunchStatus()
  }, [isOpen, justUpdated])

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    if (isOpen) {
      document.addEventListener("keydown", handleEscape)
      document.body.style.overflow = "hidden"
    }
    return () => {
      document.removeEventListener("keydown", handleEscape)
      document.body.style.overflow = "unset"
    }
  }, [isOpen, onClose])

  const handleSendTestAlert = async () => {
    setIsSendingAlert(true)
    setAlertError(null)
    
    try {
      const token = localStorage.getItem('access_token')
      const response = await fetch("/v1/test-alert", {
        method: "POST",
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      
      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || "Failed to send test alert")
      }
      
      setLastTestAlert(new Date().toLocaleString())
    } catch (error) {
      setAlertError(error instanceof Error ? error.message : "Failed to send test alert")
    } finally {
      setIsSendingAlert(false)
    }
  }

  const handleCopy = (text: string, item: string) => {
    navigator.clipboard.writeText(text)
    setCopiedItem(item)
    setTimeout(() => setCopiedItem(null), 2000)
  }

  const handleGenerateQR = async () => {
    if (!qrAlias.trim()) return
    
    setQrError(null)
    setShowQrCode(false)
    
    try {
      const response = await fetch(`/v1/enrollment-qr-payload?alias=${encodeURIComponent(qrAlias.trim())}`)
      
      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || "Failed to generate QR code")
      }
      
      const payload = await response.json()
      setQrPayload(JSON.stringify(payload))
      setShowQrCode(true)
    } catch (error) {
      setQrError(error instanceof Error ? error.message : "Failed to generate QR code")
    }
  }

  const handleAutoRelaunchToggle = (value: boolean) => {
    setPendingAutoRelaunchValue(value)
    setShowAutoRelaunchDialog(true)
  }

  const handleConfirmAutoRelaunch = async () => {
    setIsUpdatingAutoRelaunch(true)
    
    try {
      const token = localStorage.getItem('access_token')
      const response = await fetch("/v1/devices/settings/bulk", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`,
        },
        body: JSON.stringify({
          auto_relaunch_enabled: pendingAutoRelaunchValue,
        }),
      })
      
      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || "Failed to update auto-relaunch settings")
      }
      
      const result = await response.json()
      setAutoRelaunchEnabled(pendingAutoRelaunchValue)
      setJustUpdated(true)
      setTimeout(() => setJustUpdated(false), 2000)
      toast.success(result.message || `Auto-relaunch ${pendingAutoRelaunchValue ? 'enabled' : 'disabled'} for all devices`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to update auto-relaunch settings")
    } finally {
      setIsUpdatingAutoRelaunch(false)
      setShowAutoRelaunchDialog(false)
    }
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
            {/* User Info & Logout */}
            <section className="mb-8">
              <h3 className="mb-4 text-sm font-semibold">Account</h3>
              <div className="space-y-3">
                <div className="flex items-center gap-3 rounded-lg border border-border bg-muted/50 p-3">
                  <User className="h-4 w-4 text-muted-foreground" />
                  <div className="flex-1">
                    <p className="text-sm font-medium">{user?.username || 'Guest'}</p>
                    <p className="text-xs text-muted-foreground">Administrator</p>
                  </div>
                </div>
                <Button
                  variant="outline"
                  className="w-full gap-2 text-rose-600 hover:bg-rose-50 hover:text-rose-700 dark:hover:bg-rose-950/20"
                  onClick={async () => {
                    await logout()
                    toast.success('Logged out successfully')
                    onClose()
                  }}
                >
                  <LogOut className="h-4 w-4" />
                  Sign Out
                </Button>
              </div>
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

            {/* Device-Wide Auto-Relaunch */}
            <section className="mb-8">
              <h3 className="mb-4 text-sm font-semibold">Device-Wide Auto-Relaunch</h3>
              <p className="mb-4 text-sm text-muted-foreground">
                Automatically relaunch the monitored app when it goes down on all devices.
              </p>
              <div className="space-y-3">
                <div className="flex items-center justify-between rounded-lg border border-border bg-muted/50 p-3">
                  <div>
                    <p className="text-sm font-medium">Auto-Relaunch All Devices</p>
                    <p className="text-xs text-muted-foreground">
                      {autoRelaunchEnabled ? 'Enabled' : 'Disabled'} for all devices
                    </p>
                  </div>
                  <button
                    onClick={() => handleAutoRelaunchToggle(!autoRelaunchEnabled)}
                    disabled={isUpdatingAutoRelaunch}
                    className={`relative h-6 w-11 rounded-full transition-colors ${
                      autoRelaunchEnabled ? 'bg-emerald-500' : 'bg-muted'
                    } ${isUpdatingAutoRelaunch ? 'opacity-50' : ''}`}
                  >
                    <span
                      className={`absolute top-1 h-4 w-4 rounded-full bg-background transition-transform ${
                        autoRelaunchEnabled ? 'translate-x-6' : 'translate-x-1'
                      }`}
                    />
                  </button>
                </div>
                <p className="text-xs text-amber-600">
                  Note: This will update the auto-relaunch setting for all devices currently under management.
                </p>
              </div>
            </section>

            {/* Discord */}
            <section className="mb-8">
              <h3 className="mb-4 text-sm font-semibold">Discord Alerts</h3>
              <div className="space-y-3">
                <Button 
                  onClick={handleSendTestAlert} 
                  className="w-full"
                  disabled={isSendingAlert}
                >
                  {isSendingAlert ? "Sending..." : "Send Test Alert"}
                </Button>
                {lastTestAlert && (
                  <p className="text-xs text-emerald-600">✓ Test alert sent: {lastTestAlert}</p>
                )}
                {alertError && (
                  <p className="text-xs text-rose-600">✗ Error: {alertError}</p>
                )}
                <p className="text-xs text-muted-foreground">
                  Webhook configured in Replit Secrets
                </p>
              </div>
            </section>

            {/* Step 1: Install QR */}
            <section className="mb-8">
              <h3 className="mb-4 text-sm font-semibold">Step 1: Install NexMDM App</h3>
              <p className="mb-4 text-sm text-muted-foreground">
                Scan this QR code with your phone camera to download and install the NexMDM app.
              </p>
              
              <div className="space-y-3">
                <Button
                  onClick={() => setShowInstallQR(!showInstallQR)}
                  className="w-full"
                >
                  <QrCode className="mr-2 h-4 w-4" />
                  {showInstallQR ? "Hide Install QR" : "Show Install QR"}
                </Button>
                
                {showInstallQR && installUrl && (
                  <div className="flex flex-col items-center rounded-lg border border-border bg-white p-4">
                    <QRCodeSVG
                      value={installUrl}
                      size={200}
                      level="M"
                    />
                    <p className="mt-3 text-center text-xs text-muted-foreground">
                      Scan with phone camera to download APK
                    </p>
                    <p className="mt-2 text-center text-xs text-amber-600">
                      Note: You may need to enable "Install from Unknown Sources"
                    </p>
                  </div>
                )}
              </div>
            </section>

            {/* Step 2: QR Code Enrollment */}
            <section className="mb-8">
              <h3 className="mb-4 text-sm font-semibold">Step 2: Enroll Device</h3>
              <p className="mb-4 text-sm text-muted-foreground">
                After installing the app, generate an enrollment QR code to register the device.
              </p>
              
              <div className="space-y-3">
                <div>
                  <label className="mb-2 block text-sm text-muted-foreground">Device Alias</label>
                  <input
                    type="text"
                    value={qrAlias}
                    onChange={(e) => setQrAlias(e.target.value)}
                    placeholder="e.g., RackA-07"
                    className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                  />
                </div>
                
                <Button
                  onClick={handleGenerateQR}
                  className="w-full"
                  disabled={!qrAlias.trim()}
                >
                  <QrCode className="mr-2 h-4 w-4" />
                  Generate QR Code
                </Button>
                
                {qrError && (
                  <p className="text-xs text-rose-600">✗ Error: {qrError}</p>
                )}
                
                {showQrCode && qrPayload && (
                  <div className="flex flex-col items-center rounded-lg border border-border bg-white p-4">
                    <QRCodeSVG
                      value={qrPayload}
                      size={200}
                      level="M"
                    />
                    <p className="mt-3 text-center text-xs text-muted-foreground">
                      Scan with NexMDM app on Android device
                    </p>
                  </div>
                )}
              </div>
            </section>

            {/* ADB Enrollment */}
            <section className="mb-8">
              <h3 className="mb-4 text-sm font-semibold">ADB Enrollment</h3>
              <p className="mb-4 text-sm text-muted-foreground">
                Alternative enrollment method using USB and ADB commands.
              </p>

              <div className="mb-4 space-y-3">
                <div>
                  <p className="mb-2 text-xs font-medium text-muted-foreground">Single Device</p>
                  <Button
                    variant="outline"
                    className="w-full justify-between bg-transparent font-mono text-xs"
                    onClick={() => handleCopy("./enroll_device.sh \"Device-01\" \"com.ookla.speedtest.android\"", "single")}
                  >
                    <span className="truncate">./enroll_device.sh "Device-01"</span>
                    {copiedItem === "single" ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                  </Button>
                </div>

                <div>
                  <p className="mb-2 text-xs font-medium text-muted-foreground">Bulk Enrollment</p>
                  <Button
                    variant="outline"
                    className="w-full justify-between bg-transparent font-mono text-xs"
                    onClick={() => handleCopy("./bulk_enroll.sh", "bulk")}
                  >
                    <span>./bulk_enroll.sh</span>
                    {copiedItem === "bulk" ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                  </Button>
                  <p className="mt-1 text-xs text-muted-foreground">Requires devices.csv file</p>
                </div>
              </div>

              <div className="space-y-3">
                <div className="rounded-lg bg-muted p-3">
                  <p className="mb-1 text-xs font-medium">SERVER_URL</p>
                  <code className="text-xs text-muted-foreground break-all">https://628b02e5-4895-4870-9281-e541294fbe81-00-lk7z8wij3ttr.picard.replit.dev</code>
                </div>

                <div className="rounded-lg bg-muted p-3">
                  <p className="mb-1 text-xs font-medium">ADMIN_KEY</p>
                  <code className="text-xs text-muted-foreground">Configured in Replit Secrets</code>
                </div>
              </div>

              <p className="mt-3 text-xs text-muted-foreground">
                Enrollment scripts are located in the /scripts directory. Export SERVER_URL and ADMIN_KEY before running.
              </p>
            </section>

            {/* Complete Setup Script */}
            <section className="mb-8">
              <h3 className="mb-4 text-sm font-semibold">Complete Setup & Enrollment (ADB One-Liner)</h3>
              <p className="mb-4 text-sm text-muted-foreground">
                This script combines device optimization, app installation, and enrollment in one command.
              </p>
              
              <div className="space-y-3">
                <div>
                  <p className="mb-2 text-xs font-medium text-muted-foreground">Setup Script</p>
                  <Button
                    variant="outline"
                    className="w-full justify-between bg-transparent font-mono text-xs"
                    onClick={() => handleCopy("./scripts/setup_and_enroll.sh \"Device-01\"", "setup-script")}
                  >
                    <span className="truncate">./scripts/setup_and_enroll.sh "Device-01"</span>
                    {copiedItem === "setup-script" ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                  </Button>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Optimizes settings, installs APK, and enrolls device. Replace "Device-01" with your device alias.
                  </p>
                </div>

                <div className="rounded-lg border border-border bg-muted/50 p-3">
                  <p className="mb-2 text-xs font-medium">What this script does:</p>
                  <ul className="space-y-1 text-xs text-muted-foreground">
                    <li>✓ Optimizes device settings (animations, wake, etc.)</li>
                    <li>✓ Removes bloatware and unnecessary apps</li>
                    <li>✓ Downloads and installs NexMDM APK</li>
                    <li>✓ Registers device with backend</li>
                    <li>✓ Configures monitoring service</li>
                  </ul>
                </div>

                <div className="rounded-lg bg-muted p-3">
                  <p className="mb-1 text-xs font-medium">Required Environment Variables</p>
                  <code className="block text-xs text-muted-foreground">
                    export SERVER_URL="{typeof window !== 'undefined' ? window.location.origin : ''}"
                  </code>
                  <code className="block text-xs text-muted-foreground mt-1">
                    export ADMIN_KEY="your-admin-key"
                  </code>
                </div>
              </div>
            </section>

            {/* Android Permissions */}
            <section>
              <h3 className="mb-4 text-sm font-semibold">Required Android Permissions</h3>
              <p className="mb-3 text-sm text-muted-foreground">
                After enrolling, grant these permissions manually on each device:
              </p>
              <ol className="space-y-2 text-sm text-muted-foreground">
                <li>1. Settings → Apps → Special access → Usage access → NexMDM (Enable)</li>
              </ol>
              <p className="mt-3 text-xs text-muted-foreground">
                This permission allows the MDM agent to detect Unity app status and send accurate heartbeats.
              </p>
            </section>
          </div>
        </div>
      </div>

      <AlertDialog open={showAutoRelaunchDialog} onOpenChange={setShowAutoRelaunchDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {pendingAutoRelaunchValue ? 'Enable' : 'Disable'} Auto-Relaunch for All Devices?
            </AlertDialogTitle>
            <AlertDialogDescription>
              {pendingAutoRelaunchValue ? (
                <>
                  This will enable auto-relaunch for all devices currently under management. 
                  When the monitored app goes down, it will be automatically relaunched on the next heartbeat (within 5 minutes).
                </>
              ) : (
                <>
                  This will disable auto-relaunch for all devices currently under management. 
                  The monitored app will no longer be automatically relaunched when it goes down.
                </>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleConfirmAutoRelaunch} disabled={isUpdatingAutoRelaunch}>
              {isUpdatingAutoRelaunch ? (
                <>
                  <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                  Updating...
                </>
              ) : (
                'Confirm'
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
