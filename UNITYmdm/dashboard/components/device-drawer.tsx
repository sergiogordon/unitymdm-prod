"use client"

import { useEffect, useState } from "react"
import { X, Trash2, Pencil, Check, XIcon, Activity, Battery, Wifi, Bell, UserCheck, AlertTriangle, Network, RotateCw, Power } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { formatTimestampCST } from "@/lib/utils"
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
import type { Device } from "@/lib/api"

interface DeviceDrawerProps {
  device: Device | null
  isOpen: boolean
  onClose: () => void
  onDeviceDeleted?: () => void
  onDeviceUpdated?: () => void
}

interface DeviceEvent {
  id: number
  event_type: string
  timestamp: string
  details: any
}

export function DeviceDrawer({ device, isOpen, onClose, onDeviceDeleted, onDeviceUpdated }: DeviceDrawerProps) {
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [isEditingAlias, setIsEditingAlias] = useState(false)
  const [editedAlias, setEditedAlias] = useState("")
  const [isSavingAlias, setIsSavingAlias] = useState(false)
  const [events, setEvents] = useState<DeviceEvent[]>([])
  const [loadingEvents, setLoadingEvents] = useState(false)
  const [showAllEvents, setShowAllEvents] = useState(false)
  const [showRestartAppDialog, setShowRestartAppDialog] = useState(false)
  const [showRebootDialog, setShowRebootDialog] = useState(false)
  const [isRestarting, setIsRestarting] = useState(false)
  const [monitoredPackage, setMonitoredPackage] = useState("")
  const [monitoredAppName, setMonitoredAppName] = useState("")
  const [autoRelaunchEnabled, setAutoRelaunchEnabled] = useState(false)
  const [isEditingSettings, setIsEditingSettings] = useState(false)
  const [isSavingSettings, setIsSavingSettings] = useState(false)

  useEffect(() => {
    if (device) {
      setEditedAlias(device.alias)
      setIsEditingAlias(false)
      setMonitoredPackage(device.monitored_package || "org.zwanoo.android.speedtest")
      setMonitoredAppName(device.monitored_app_name || "Speedtest")
      setAutoRelaunchEnabled(device.auto_relaunch_enabled || false)
      setIsEditingSettings(false)
      fetchEvents()
    }
  }, [device])

  const fetchEvents = async () => {
    if (!device) return
    
    setLoadingEvents(true)
    try {
      const token = localStorage.getItem('access_token')
      const response = await fetch(`/v1/devices/${device.id}/events?limit=20`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      })
      if (response.ok) {
        const data = await response.json()
        setEvents(data)
      }
    } catch (error) {
      console.error('Failed to fetch device events:', error)
    } finally {
      setLoadingEvents(false)
    }
  }

  const getEventIcon = (eventType: string) => {
    switch (eventType) {
      case 'device_enrolled':
        return <UserCheck className="h-4 w-4 text-green-600" />
      case 'status_change':
        return <Activity className="h-4 w-4 text-blue-600" />
      case 'battery_low':
      case 'battery_critical':
        return <Battery className="h-4 w-4 text-orange-600" />
      case 'network_change':
        return <Network className="h-4 w-4 text-purple-600" />
      case 'ping_sent':
      case 'ping_response':
        return <Wifi className="h-4 w-4 text-indigo-600" />
      case 'ring_sent':
        return <Bell className="h-4 w-4 text-yellow-600" />
      case 'alias_changed':
        return <Pencil className="h-4 w-4 text-teal-600" />
      case 'device_deleted':
        return <Trash2 className="h-4 w-4 text-red-600" />
      default:
        return <Activity className="h-4 w-4 text-gray-600" />
    }
  }

  const getEventDescription = (event: DeviceEvent) => {
    const details = event.details || {}
    
    switch (event.event_type) {
      case 'device_enrolled':
        return `Device enrolled as "${details.alias}"`
      case 'status_change':
        return `Status changed: ${details.from} → ${details.to}${details.offline_duration_seconds ? ` (offline for ${Math.floor(details.offline_duration_seconds / 60)}m)` : ''}`
      case 'battery_low':
        return `Battery low: ${details.level}%`
      case 'battery_critical':
        return `Battery critical: ${details.level}%`
      case 'network_change':
        return `Network changed: ${details.from} → ${details.to}${details.ssid ? ` (${details.ssid})` : details.carrier ? ` (${details.carrier})` : ''}`
      case 'ping_sent':
        return 'Ping sent to device'
      case 'ping_response':
        return `Ping response: ${details.latency_ms}ms`
      case 'ring_sent':
        return `Ring sent (${details.duration}s duration)`
      case 'alias_changed':
        return `Alias changed: "${details.old_alias}" → "${details.new_alias}"`
      case 'device_deleted':
        return `Device "${details.alias}" deleted`
      default:
        return event.event_type
    }
  }

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (isEditingAlias) {
          setIsEditingAlias(false)
          setEditedAlias(device?.alias || "")
        } else {
          onClose()
        }
      }
    }
    if (isOpen) {
      document.addEventListener("keydown", handleEscape)
      document.body.style.overflow = "hidden"
    }
    return () => {
      document.removeEventListener("keydown", handleEscape)
      document.body.style.overflow = "unset"
    }
  }, [isOpen, onClose, isEditingAlias, device])

  const handleSaveAlias = async () => {
    if (!device || !editedAlias.trim()) {
      toast.error("Alias cannot be empty")
      return
    }

    if (editedAlias.trim() === device.alias) {
      setIsEditingAlias(false)
      return
    }

    setIsSavingAlias(true)
    try {
      const token = localStorage.getItem('access_token')
      const response = await fetch(`/v1/devices/${device.id}/alias`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ alias: editedAlias.trim() }),
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || 'Failed to update alias')
      }

      const data = await response.json()
      toast.success(data.message || 'Alias updated successfully')
      setIsEditingAlias(false)
      onDeviceUpdated?.()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to update alias')
      setEditedAlias(device.alias)
    } finally {
      setIsSavingAlias(false)
    }
  }

  const handleDelete = async () => {
    if (!device) return
    
    setIsDeleting(true)
    try {
      const token = localStorage.getItem('access_token')
      const response = await fetch(`/v1/devices/${device.id}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      
      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.error || 'Failed to delete device')
      }
      
      toast.success(`${device.alias} deleted successfully`)
      onClose()
      onDeviceDeleted?.()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to delete device')
    } finally {
      setIsDeleting(false)
    }
  }

  const handleRestartApp = async () => {
    if (!device) return
    
    setIsRestarting(true)
    setShowRestartAppDialog(false)
    
    try {
      const token = localStorage.getItem('access_token')
      const headers: HeadersInit = {
        'Content-Type': 'application/json',
      }
      if (token) {
        headers['Authorization'] = `Bearer ${token}`
      }

      const response = await fetch('/v1/remote/restart-app', {
        method: 'POST',
        headers,
        body: JSON.stringify({ device_ids: [device.id] })
      })

      if (!response.ok) {
        throw new Error('Failed to send restart command')
      }

      const data = await response.json()
      if (data.ok && data.success_count > 0) {
        toast.success(`App restart command sent to ${device.alias}`)
      } else {
        toast.error(`Failed to restart app on ${device.alias}`)
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to send restart command')
    } finally {
      setIsRestarting(false)
    }
  }

  const handleReboot = async () => {
    if (!device) return
    
    setIsRestarting(true)
    setShowRebootDialog(false)
    
    try {
      const token = localStorage.getItem('access_token')
      const headers: HeadersInit = {
        'Content-Type': 'application/json',
      }
      if (token) {
        headers['Authorization'] = `Bearer ${token}`
      }

      const response = await fetch('/v1/remote/reboot', {
        method: 'POST',
        headers,
        body: JSON.stringify({ device_ids: [device.id] })
      })

      if (!response.ok) {
        throw new Error('Failed to send reboot command')
      }

      const data = await response.json()
      if (data.ok && data.success_count > 0) {
        toast.success(`Reboot command sent to ${device.alias}`)
      } else {
        toast.error(`Failed to reboot ${device.alias}`)
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to send reboot command')
    } finally {
      setIsRestarting(false)
    }
  }

  const handleSaveSettings = async () => {
    if (!device || !monitoredPackage.trim()) {
      toast.error("Monitored package cannot be empty")
      return
    }

    setIsSavingSettings(true)
    try {
      const token = localStorage.getItem('access_token')
      const response = await fetch(`/v1/devices/${device.id}/settings`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          monitored_package: monitoredPackage.trim(),
          monitored_app_name: monitoredAppName.trim(),
          auto_relaunch_enabled: autoRelaunchEnabled
        }),
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || 'Failed to update settings')
      }

      toast.success("Device settings updated successfully")
      setIsEditingSettings(false)
      if (onDeviceUpdated) onDeviceUpdated()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to update settings')
    } finally {
      setIsSavingSettings(false)
    }
  }

  if (!isOpen || !device) return null

  const battery = device.last_status?.battery?.pct ?? 0
  const charging = device.last_status?.battery?.charging ?? false
  const network = device.last_status?.network?.transport === 'wifi' 
    ? `WiFi • ${device.last_status?.network?.ssid || 'Unknown'}`
    : `Cellular • ${device.last_status?.network?.carrier || 'Unknown'}`
  
  // Use monitored_package to dynamically look up app info
  const monitoredApp = device.last_status?.app_versions?.[device.monitored_package]
  const monitoredAppVersion = monitoredApp?.version_name || 'Not installed'
  const monitoredAppInstalled = monitoredApp?.installed ?? false
  
  const isSpeedtest = device.monitored_package === 'org.zwanoo.android.speedtest'
  const speedtestRunning = isSpeedtest 
    ? (device.last_status?.speedtest_running_signals?.has_service_notification ?? false)
    : null
  const foregroundSeconds = isSpeedtest 
    ? (device.last_status?.speedtest_running_signals?.foreground_recent_seconds ?? 0)
    : -1
  const monitoredAppStatus = isSpeedtest 
    ? (speedtestRunning ? 'running' : (foregroundSeconds === -1 ? 'permission needed' : 'down'))
    : 'n/a'
  const uptime = device.last_status?.system?.uptime_seconds 
    ? `${Math.floor(device.last_status.system.uptime_seconds / 3600)}h`
    : '-'
  const lastSeen = formatTimestampCST(device.last_seen, { addSuffix: true })

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/20 backdrop-blur-sm" onClick={onClose} />
      <div className="fixed right-0 top-0 z-50 h-full w-full max-w-[480px] animate-in slide-in-from-right">
        <div className="flex h-full flex-col bg-card shadow-2xl">
          <div className="flex items-center justify-between border-b border-border px-6 py-4">
            {isEditingAlias ? (
              <div className="flex flex-1 items-center gap-2">
                <input
                  type="text"
                  value={editedAlias}
                  onChange={(e) => setEditedAlias(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleSaveAlias()
                  }}
                  className="flex-1 rounded-md border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                  placeholder="Device alias"
                  autoFocus
                  disabled={isSavingAlias}
                />
                <Button 
                  variant="ghost" 
                  size="icon" 
                  onClick={handleSaveAlias}
                  disabled={isSavingAlias}
                >
                  <Check className="h-4 w-4 text-green-600" />
                </Button>
                <Button 
                  variant="ghost" 
                  size="icon" 
                  onClick={() => {
                    setIsEditingAlias(false)
                    setEditedAlias(device.alias)
                  }}
                  disabled={isSavingAlias}
                >
                  <XIcon className="h-4 w-4 text-red-600" />
                </Button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-semibold">{device.alias}</h2>
                <Button 
                  variant="ghost" 
                  size="icon" 
                  onClick={() => setIsEditingAlias(true)}
                  className="h-8 w-8"
                >
                  <Pencil className="h-3.5 w-3.5" />
                </Button>
              </div>
            )}
            <Button variant="ghost" size="icon" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          </div>

          <div className="flex-1 overflow-y-auto p-6">
            <div className="mb-6 space-y-4 rounded-lg bg-muted/50 p-4">
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Status</span>
                <div className="flex items-center gap-2">
                  <div
                    className={`h-2 w-2 rounded-full ${
                      device.status === "online" ? "bg-status-online" : "bg-status-offline"
                    }`}
                  />
                  <span className="text-sm font-medium capitalize">{device.status}</span>
                </div>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Last Seen</span>
                <span className="text-sm font-medium">{lastSeen}</span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">APK Version</span>
                <span className="text-sm font-medium font-mono">{device.app_version || '-'}</span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Battery</span>
                <span className="text-sm font-medium">
                  {battery}%{charging && " (Charging)"}
                </span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Network</span>
                <span className="text-sm font-medium">{network}</span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">{device.monitored_app_name}</span>
                <span className="text-sm font-medium">
                  {monitoredAppVersion} ({monitoredAppStatus})
                </span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Uptime</span>
                <span className="text-sm font-medium">{uptime}</span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Device Owner</span>
                <div className="flex items-center gap-2">
                  {device.is_device_owner ? (
                    <>
                      <div className="h-2 w-2 rounded-full bg-green-500" />
                      <span className="text-sm font-medium text-green-600">Enrolled</span>
                    </>
                  ) : (
                    <>
                      <div className="h-2 w-2 rounded-full bg-yellow-500" />
                      <span className="text-sm font-medium text-yellow-600">Not Enrolled</span>
                    </>
                  )}
                </div>
              </div>
            </div>

            <div className="mb-6 rounded-lg bg-muted/50 p-4">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-medium">Device Settings</h3>
                {!isEditingSettings ? (
                  <Button 
                    variant="ghost" 
                    size="sm" 
                    onClick={() => setIsEditingSettings(true)}
                    className="h-7 px-2 text-xs"
                  >
                    <Pencil className="h-3 w-3 mr-1" />
                    Edit
                  </Button>
                ) : (
                  <div className="flex gap-1">
                    <Button 
                      variant="ghost" 
                      size="sm" 
                      onClick={handleSaveSettings}
                      disabled={isSavingSettings}
                      className="h-7 px-2 text-xs text-green-600 hover:text-green-700"
                    >
                      <Check className="h-3 w-3 mr-1" />
                      Save
                    </Button>
                    <Button 
                      variant="ghost" 
                      size="sm" 
                      onClick={() => {
                        setIsEditingSettings(false)
                        setMonitoredPackage(device?.monitored_package || "org.zwanoo.android.speedtest")
                        setMonitoredAppName(device?.monitored_app_name || "Speedtest")
                        setAutoRelaunchEnabled(device?.auto_relaunch_enabled || false)
                      }}
                      disabled={isSavingSettings}
                      className="h-7 px-2 text-xs text-red-600 hover:text-red-700"
                    >
                      <XIcon className="h-3 w-3 mr-1" />
                      Cancel
                    </Button>
                  </div>
                )}
              </div>

              <div className="space-y-4">
                <div>
                  <label className="block text-xs text-muted-foreground mb-2">
                    Monitored App Name
                  </label>
                  {isEditingSettings ? (
                    <input
                      type="text"
                      value={monitoredAppName}
                      onChange={(e) => setMonitoredAppName(e.target.value)}
                      className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                      placeholder="Unity"
                      disabled={isSavingSettings}
                    />
                  ) : (
                    <div className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm text-muted-foreground">
                      {monitoredAppName || "Speedtest"}
                    </div>
                  )}
                  <p className="mt-1 text-xs text-muted-foreground">
                    Display name for the monitored app (e.g., Unity, Speedtest)
                  </p>
                </div>

                <div>
                  <label className="block text-xs text-muted-foreground mb-2">
                    Monitored App Package
                  </label>
                  {isEditingSettings ? (
                    <input
                      type="text"
                      value={monitoredPackage}
                      onChange={(e) => setMonitoredPackage(e.target.value)}
                      className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-ring"
                      placeholder="com.example.app"
                      disabled={isSavingSettings}
                    />
                  ) : (
                    <div className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm font-mono text-muted-foreground">
                      {monitoredPackage || "org.zwanoo.android.speedtest"}
                    </div>
                  )}
                  <p className="mt-1 text-xs text-muted-foreground">
                    Package name of the app to monitor (e.g., org.zwanoo.android.speedtest or Unity app)
                  </p>
                </div>

                <div className="flex items-center justify-between">
                  <div>
                    <label className="block text-xs text-muted-foreground mb-1">
                      Auto-Relaunch
                    </label>
                    <p className="text-xs text-muted-foreground">
                      Automatically relaunch app if it goes down
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => isEditingSettings && setAutoRelaunchEnabled(!autoRelaunchEnabled)}
                    disabled={!isEditingSettings || isSavingSettings}
                    className={`relative h-6 w-11 rounded-full transition-colors ${
                      autoRelaunchEnabled ? "bg-green-500" : "bg-muted"
                    } ${!isEditingSettings || isSavingSettings ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}
                  >
                    <span
                      className={`absolute top-1 h-4 w-4 rounded-full bg-white transition-transform ${
                        autoRelaunchEnabled ? "left-6" : "left-1"
                      }`}
                    />
                  </button>
                </div>
              </div>
            </div>

            {!device.is_device_owner && (
              <div className="mb-6 rounded-lg border border-yellow-200 bg-yellow-50 dark:border-yellow-900 dark:bg-yellow-950/30 p-4">
                <div className="flex items-start gap-3">
                  <div className="mt-0.5">
                    <svg className="h-5 w-5 text-yellow-600 dark:text-yellow-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                  </div>
                  <div className="flex-1">
                    <h4 className="text-sm font-semibold text-yellow-800 dark:text-yellow-400 mb-2">
                      Device Owner Not Enrolled
                    </h4>
                    <p className="text-xs text-yellow-700 dark:text-yellow-500 mb-3">
                      This device is not enrolled as Device Owner. Silent APK installation will not work without Device Owner privileges.
                    </p>
                    <div className="rounded-md bg-yellow-100 dark:bg-yellow-900/50 p-3">
                      <p className="text-xs font-medium text-yellow-900 dark:text-yellow-300 mb-2">
                        To enroll as Device Owner:
                      </p>
                      <ol className="text-xs text-yellow-800 dark:text-yellow-400 space-y-1 list-decimal list-inside">
                        <li>Factory reset the device</li>
                        <li>Connect via ADB: <code className="bg-yellow-200 dark:bg-yellow-800 px-1 rounded">adb shell dpm set-device-owner com.nexmdm/.NexDeviceAdminReceiver</code></li>
                        <li>Complete device setup and enroll via QR or ADB script</li>
                      </ol>
                    </div>
                  </div>
                </div>
              </div>
            )}

            <div className="mb-6">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-medium">Activity Timeline</h3>
                {events.length > 10 && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setShowAllEvents(!showAllEvents)}
                    className="text-xs h-7"
                  >
                    {showAllEvents ? 'Show Less' : `Show All (${events.length})`}
                  </Button>
                )}
              </div>
              {loadingEvents ? (
                <div className="flex items-center justify-center py-8">
                  <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                </div>
              ) : events.length === 0 ? (
                <div className="rounded-lg bg-muted/50 p-4 text-center text-sm text-muted-foreground">
                  No activity recorded yet
                </div>
              ) : (
                <div className="space-y-3">
                  {(showAllEvents ? events : events.slice(0, 10)).map((event, index) => (
                    <div key={event.id} className="flex gap-3">
                      <div className="flex flex-col items-center">
                        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-muted">
                          {getEventIcon(event.event_type)}
                        </div>
                        {index < (showAllEvents ? events : events.slice(0, 10)).length - 1 && (
                          <div className="h-full w-px bg-border" />
                        )}
                      </div>
                      <div className="flex-1 pb-4">
                        <p className="text-sm font-medium">{getEventDescription(event)}</p>
                        <p className="text-xs text-muted-foreground">
                          {formatTimestampCST(event.timestamp, { addSuffix: true })}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div>
              <h3 className="mb-3 text-sm font-medium">Device Details</h3>
              <pre className="overflow-x-auto rounded-lg bg-muted p-4 text-xs font-mono">
                {JSON.stringify(device, null, 2)}
              </pre>
            </div>
          </div>

          <div className="border-t border-border p-6 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <Button
                variant="outline"
                onClick={() => setShowRestartAppDialog(true)}
                disabled={isRestarting || device.status === 'offline'}
                className="border-yellow-600 text-yellow-600 hover:bg-yellow-50 dark:hover:bg-yellow-950"
              >
                <RotateCw className="h-4 w-4" />
                Restart App
              </Button>
              <Button
                variant="outline"
                onClick={() => setShowRebootDialog(true)}
                disabled={isRestarting || device.status === 'offline' || !device.is_device_owner}
                className="border-red-600 text-red-600 hover:bg-red-50 dark:hover:bg-red-950"
              >
                <Power className="h-4 w-4" />
                Reboot
              </Button>
            </div>
            <Button
              variant="destructive"
              className="w-full"
              onClick={() => setShowDeleteDialog(true)}
              disabled={isDeleting}
            >
              <Trash2 className="h-4 w-4" />
              Delete Device
            </Button>
          </div>
        </div>
      </div>

      <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Device</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete <strong>{device?.alias}</strong>? This action cannot be undone and will permanently remove the device from the system.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              disabled={isDeleting}
              className="bg-destructive text-white hover:bg-destructive/90"
            >
              {isDeleting ? 'Deleting...' : 'Delete'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={showRestartAppDialog} onOpenChange={setShowRestartAppDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Restart UNITYmdm App?</AlertDialogTitle>
            <AlertDialogDescription>
              This will perform a soft restart of the UNITYmdm app on <strong>{device?.alias}</strong>.
              <br /><br />
              <span className="font-medium">What happens:</span>
              <ul className="list-disc list-inside mt-2 space-y-1">
                <li>App will stop and restart automatically</li>
                <li>Device will be back online in ~10 seconds</li>
                <li>All monitoring will resume automatically</li>
                <li>No interruption to other device functions</li>
              </ul>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction 
              onClick={handleRestartApp}
              className="bg-yellow-600 hover:bg-yellow-700"
              disabled={isRestarting}
            >
              {isRestarting ? 'Restarting...' : 'Restart App'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={showRebootDialog} onOpenChange={setShowRebootDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Reboot Device?</AlertDialogTitle>
            <AlertDialogDescription>
              This will perform a <span className="font-semibold text-red-600">hard restart</span> of <strong>{device?.alias}</strong>.
              <br /><br />
              <span className="font-medium">What happens:</span>
              <ul className="list-disc list-inside mt-2 space-y-1">
                <li>Entire device will reboot immediately</li>
                <li>All apps and processes will be interrupted</li>
                <li>Device will be back online in ~30-60 seconds</li>
                <li>Monitoring will auto-resume after boot</li>
              </ul>
              <br />
              <span className="text-red-600 font-medium">⚠️ Use only when necessary (frozen devices, critical issues)</span>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction 
              onClick={handleReboot}
              className="bg-red-600 hover:bg-red-700"
              disabled={isRestarting}
            >
              {isRestarting ? 'Rebooting...' : 'Reboot Device'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
