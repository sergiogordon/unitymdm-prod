"use client"

import { AlertTriangle, Battery, Wifi, WifiOff } from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import type { Device } from "@/lib/api"

interface AlertsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  devices: Device[]
  onSelectDevice: (device: Device) => void
}

export function AlertsDialog({ open, onOpenChange, devices, onSelectDevice }: AlertsDialogProps) {
  const alertDevices = devices.filter(d => {
    if (!d.last_status) return d.status === 'offline'
    const battery = d.last_status.battery?.pct || 100
    const monitoredApp = d.monitored_package ? d.last_status.app_versions?.[d.monitored_package] : null
    const monitoredAppInstalled = monitoredApp?.installed || false
    
    const isSpeedtest = d.monitored_package === 'org.zwanoo.android.speedtest'
    const monitoredAppRunning = isSpeedtest 
      ? (d.last_status.speedtest_running_signals?.has_service_notification || false)
      : null
    const foregroundSeconds = isSpeedtest 
      ? (d.last_status.speedtest_running_signals?.foreground_recent_seconds ?? 0)
      : -1
    
    // Only alert if monitored app is not running AND we have permission to check (foregroundSeconds !== -1)
    // For non-Speedtest apps, skip running status checks since we don't have that data
    const shouldAlertApp = isSpeedtest && (!monitoredAppInstalled || (!monitoredAppRunning && foregroundSeconds !== -1))
    
    return d.status === 'offline' || battery < 20 || shouldAlertApp
  })

  const getAlertReasons = (device: Device): string[] => {
    const reasons: string[] = []
    
    if (device.status === 'offline') {
      reasons.push('Device offline')
    }
    
    if (device.last_status) {
      const battery = device.last_status.battery?.pct || 100
      const monitoredApp = device.monitored_package ? device.last_status.app_versions?.[device.monitored_package] : null
      const monitoredAppInstalled = monitoredApp?.installed || false
      const isSpeedtest = device.monitored_package === 'org.zwanoo.android.speedtest'
      const monitoredAppRunning = isSpeedtest 
        ? (device.last_status.speedtest_running_signals?.has_service_notification || false)
        : null
      const foregroundSeconds = isSpeedtest 
        ? (device.last_status.speedtest_running_signals?.foreground_recent_seconds ?? 0)
        : -1
      const appName = device.monitored_app_name || 'Monitored App'
      
      if (battery < 20) {
        reasons.push(`Low battery (${battery}%)`)
      }
      
      // Only show app alerts for Speedtest (since we don't have running status for other apps)
      if (isSpeedtest) {
        if (!monitoredAppInstalled) {
          reasons.push(`${appName} not installed`)
        } else if (!monitoredAppRunning) {
          if (foregroundSeconds === -1) {
            reasons.push(`${appName} permission needed`)
          } else {
            reasons.push(`${appName} not running`)
          }
        }
      }
    }
    
    return reasons
  }

  const handleDeviceClick = (device: Device) => {
    onSelectDevice(device)
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-status-warning" />
            Active Alerts ({alertDevices.length})
          </DialogTitle>
          <DialogDescription>
            Devices requiring attention
          </DialogDescription>
        </DialogHeader>
        
        <div className="mt-4 max-h-[60vh] space-y-2 overflow-y-auto">
          {alertDevices.length === 0 ? (
            <div className="py-8 text-center text-muted-foreground">
              No active alerts
            </div>
          ) : (
            alertDevices.map((device) => {
              const reasons = getAlertReasons(device)
              
              return (
                <button
                  key={device.id}
                  onClick={() => handleDeviceClick(device)}
                  className="w-full rounded-lg border border-border bg-card p-4 text-left transition-colors hover:bg-muted/30"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{device.alias}</span>
                        {device.status === 'offline' ? (
                          <WifiOff className="h-4 w-4 text-status-offline" />
                        ) : (
                          <Wifi className="h-4 w-4 text-status-online" />
                        )}
                      </div>
                      <div className="mt-2 space-y-1">
                        {reasons.map((reason, index) => (
                          <div
                            key={index}
                            className="flex items-center gap-2 text-sm text-muted-foreground"
                          >
                            {reason.includes('battery') ? (
                              <Battery className="h-3.5 w-3.5 text-status-offline" />
                            ) : (
                              <AlertTriangle className="h-3.5 w-3.5 text-status-warning" />
                            )}
                            <span>{reason}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div className="text-sm text-muted-foreground">
                      Click to view
                    </div>
                  </div>
                </button>
              )
            })
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
