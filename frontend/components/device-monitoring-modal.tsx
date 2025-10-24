"use client"

import { useState } from "react"
import { X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useToast } from "@/hooks/use-toast"

interface DeviceMonitoringModalProps {
  isOpen: boolean
  onClose: () => void
  deviceId: string
  deviceAlias: string
  currentMonitoring?: {
    monitor_enabled: boolean
    monitored_package: string | null
    monitored_app_name: string | null
    monitored_threshold_min: number
    service_up: boolean | null
    monitored_foreground_recent_s: number | null
  }
  onUpdated?: () => void
}

export function DeviceMonitoringModal({
  isOpen,
  onClose,
  deviceId,
  deviceAlias,
  currentMonitoring,
  onUpdated
}: DeviceMonitoringModalProps) {
  const { toast } = useToast()
  const [isLoading, setIsLoading] = useState(false)
  
  const [monitorEnabled, setMonitorEnabled] = useState(currentMonitoring?.monitor_enabled ?? true)
  const [monitoredPackage, setMonitoredPackage] = useState(
    currentMonitoring?.monitored_package ?? "org.zwanoo.android.speedtest"
  )
  const [monitoredAppName, setMonitoredAppName] = useState(
    currentMonitoring?.monitored_app_name ?? "unity"
  )
  const [thresholdMin, setThresholdMin] = useState(
    currentMonitoring?.monitored_threshold_min ?? 10
  )

  const handleSave = async () => {
    setIsLoading(true)
    try {
      const token = localStorage.getItem('auth_token')
      const response = await fetch(`/api/proxy/admin/devices/${deviceId}/monitoring`, {
        method: 'PATCH',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          monitor_enabled: monitorEnabled,
          monitored_package: monitoredPackage,
          monitored_app_name: monitoredAppName,
          monitored_threshold_min: thresholdMin
        })
      })

      if (!response.ok) {
        throw new Error(`Failed to update monitoring settings: ${response.statusText}`)
      }

      toast({
        title: "Settings updated",
        description: "Monitoring configuration saved successfully",
        variant: "default"
      })
      
      onUpdated?.()
      onClose()
    } catch (error) {
      toast({
        title: "Update failed",
        description: error instanceof Error ? error.message : "Failed to update monitoring settings",
        variant: "destructive"
      })
    } finally {
      setIsLoading(false)
    }
  }

  if (!isOpen) return null

  const serviceStatus = currentMonitoring?.service_up === true ? "Up" : 
                       currentMonitoring?.service_up === false ? "Down" : 
                       "Unknown"
  
  const lastForegroundStr = currentMonitoring?.monitored_foreground_recent_s != null
    ? `${Math.floor(currentMonitoring.monitored_foreground_recent_s / 60)}m ago`
    : "N/A"

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/20 backdrop-blur-sm" onClick={onClose} />
      <div className="fixed left-1/2 top-1/2 z-50 w-full max-w-lg -translate-x-1/2 -translate-y-1/2 animate-in">
        <div className="flex flex-col bg-card shadow-2xl rounded-lg border border-border">
          <div className="flex items-center justify-between border-b border-border px-6 py-4">
            <h2 className="text-lg font-semibold">Service Monitoring</h2>
            <Button variant="ghost" size="icon" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          </div>

          <div className="overflow-y-auto p-6 space-y-6">
            <div>
              <h3 className="text-sm font-medium mb-2">Device: {deviceAlias}</h3>
              {currentMonitoring && (
                <div className="space-y-1 text-sm text-muted-foreground">
                  <div className="flex justify-between">
                    <span>Current Status:</span>
                    <span className={
                      serviceStatus === "Up" ? "text-green-600" :
                      serviceStatus === "Down" ? "text-red-600" :
                      "text-yellow-600"
                    }>
                      {serviceStatus}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span>Last Foreground:</span>
                    <span>{lastForegroundStr}</span>
                  </div>
                </div>
              )}
            </div>

            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <label className="text-sm font-medium">Enable Monitoring</label>
                <button
                  onClick={() => setMonitorEnabled(!monitorEnabled)}
                  className={`relative h-6 w-11 rounded-full transition-colors ${
                    monitorEnabled ? 'bg-primary' : 'bg-muted'
                  }`}
                >
                  <span
                    className={`absolute top-1 h-4 w-4 rounded-full bg-white transition-transform ${
                      monitorEnabled ? 'left-6' : 'left-1'
                    }`}
                  />
                </button>
              </div>

              <div>
                <label className="mb-2 block text-sm font-medium">Package Name</label>
                <input
                  type="text"
                  value={monitoredPackage}
                  onChange={(e) => setMonitoredPackage(e.target.value)}
                  placeholder="org.zwanoo.android.speedtest"
                  disabled={!monitorEnabled}
                  className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm disabled:opacity-50"
                />
                <p className="mt-1 text-xs text-muted-foreground">
                  Android package name to monitor (e.g., org.zwanoo.android.speedtest, com.unity.game)
                </p>
              </div>

              <div>
                <label className="mb-2 block text-sm font-medium">Display Name</label>
                <input
                  type="text"
                  value={monitoredAppName}
                  onChange={(e) => setMonitoredAppName(e.target.value)}
                  placeholder="unity"
                  disabled={!monitorEnabled}
                  className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm disabled:opacity-50"
                />
                <p className="mt-1 text-xs text-muted-foreground">
                  Friendly name for Discord alerts
                </p>
              </div>

              <div>
                <label className="mb-2 block text-sm font-medium">Alert Threshold (minutes)</label>
                <input
                  type="number"
                  min="1"
                  max="120"
                  value={thresholdMin}
                  onChange={(e) => setThresholdMin(parseInt(e.target.value) || 10)}
                  disabled={!monitorEnabled}
                  className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm disabled:opacity-50"
                />
                <p className="mt-1 text-xs text-muted-foreground">
                  Alert if app hasn't been in foreground for this many minutes (1-120)
                </p>
              </div>
            </div>
          </div>

          <div className="flex justify-end gap-3 border-t border-border px-6 py-4">
            <Button variant="outline" onClick={onClose} disabled={isLoading}>
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={isLoading}>
              {isLoading ? "Saving..." : "Save Settings"}
            </Button>
          </div>
        </div>
      </div>
    </>
  )
}
