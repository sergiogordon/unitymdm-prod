"use client"

import { Battery, Wifi, Smartphone, Radio, Signal, Bell, RefreshCw } from "lucide-react"
import type { Device } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { useState } from "react"
import { formatTimestampCST } from "@/lib/utils"

interface DevicesTableProps {
  devices: Device[]
  onSelectDevice: (device: Device) => void
  onOpenSettings: () => void
  onPingDevice: (deviceId: string) => Promise<{ ok: boolean; message?: string; error?: string }>
  onRingDevice: (deviceId: string) => Promise<{ ok: boolean; message?: string; error?: string }>
  selectedDeviceIds?: Set<string>
  onToggleDevice?: (deviceId: string) => void
  onToggleAll?: () => void
}

export function DevicesTable({ 
  devices, 
  onSelectDevice, 
  onOpenSettings, 
  onPingDevice, 
  onRingDevice,
  selectedDeviceIds = new Set(),
  onToggleDevice,
  onToggleAll
}: DevicesTableProps) {
  const [pingStates, setPingStates] = useState<Record<string, { loading: boolean; result?: { ok: boolean; message?: string; error?: string } }>>({})
  const [ringStates, setRingStates] = useState<Record<string, { loading: boolean; result?: { ok: boolean; message?: string; error?: string } }>>({})

  const handlePing = async (e: React.MouseEvent, deviceId: string) => {
    e.stopPropagation()
    
    setPingStates(prev => ({ ...prev, [deviceId]: { loading: true } }))
    
    try {
      const result = await onPingDevice(deviceId)
      setPingStates(prev => ({ 
        ...prev, 
        [deviceId]: { loading: false, result } 
      }))
      
      setTimeout(() => {
        setPingStates(prev => ({ ...prev, [deviceId]: { loading: false } }))
      }, 20000)
    } catch (error) {
      setPingStates(prev => ({ 
        ...prev, 
        [deviceId]: { 
          loading: false, 
          result: { ok: false, error: 'Failed to ping device' } 
        } 
      }))
      
      setTimeout(() => {
        setPingStates(prev => ({ ...prev, [deviceId]: { loading: false } }))
      }, 20000)
    }
  }

  const handleRing = async (e: React.MouseEvent, deviceId: string) => {
    e.stopPropagation()
    
    setRingStates(prev => ({ ...prev, [deviceId]: { loading: true } }))
    
    try {
      const result = await onRingDevice(deviceId)
      setRingStates(prev => ({ 
        ...prev, 
        [deviceId]: { loading: false, result } 
      }))
      
      setTimeout(() => {
        setRingStates(prev => ({ ...prev, [deviceId]: { loading: false } }))
      }, result.ok ? 30000 : 5000)
    } catch (error) {
      setRingStates(prev => ({ 
        ...prev, 
        [deviceId]: { 
          loading: false, 
          result: { ok: false, error: 'Failed to ring device' } 
        } 
      }))
      
      setTimeout(() => {
        setRingStates(prev => ({ ...prev, [deviceId]: { loading: false } }))
      }, 5000)
    }
  }

  const getPingStatusDisplay = (device: Device) => {
    const pingStatus = (device as any).ping_status
    const now = Date.now()
    const THIRTY_SECONDS = 30 * 1000
    
    // Check if backend ping result is older than 30 seconds using backend timestamps
    const isPingResultExpired = () => {
      if (!pingStatus) return false
      
      // For "replied" status, use response_at timestamp
      if (pingStatus.status === "replied") {
        if (!pingStatus.response_at) return true // Hide if timestamp missing
        const responseTime = new Date(pingStatus.response_at).getTime()
        return (now - responseTime) > THIRTY_SECONDS
      }
      
      // For "no_reply" status, use sent_at timestamp + 60 seconds (timeout duration)
      if (pingStatus.status === "no_reply") {
        if (!pingStatus.sent_at) return true // Hide if timestamp missing
        const sentTime = new Date(pingStatus.sent_at).getTime()
        // Result is visible from when timeout occurs (sent_at + 60s), so add 60s to sent time
        const resultTime = sentTime + 60000
        return (now - resultTime) > THIRTY_SECONDS
      }
      
      return false
    }
    
    if (pingStates[device.id]?.loading || (pingStatus?.status === "waiting" && pingStates[device.id]?.result?.ok)) {
      return (
        <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
          <Radio className="h-3.5 w-3.5 animate-pulse" />
          {pingStatus?.status === "waiting" ? `${pingStatus.elapsed_seconds}s` : "Pinging..."}
        </span>
      )
    }
    
    // Only show ping results if they're not expired
    if (pingStatus?.status === "replied" && !isPingResultExpired()) {
      return (
        <span className="text-xs text-status-online" title={`Reply in ${pingStatus.latency_ms}ms`}>
          ✅ {pingStatus.latency_ms}ms
        </span>
      )
    }
    
    if (pingStatus?.status === "no_reply" && !isPingResultExpired()) {
      return (
        <span className="text-xs text-status-offline" title="Device did not respond to ping">
          ❌ No reply
        </span>
      )
    }
    
    if (pingStates[device.id]?.result) {
      return pingStates[device.id]?.result?.ok ? (
        <span className="text-xs text-status-online">✅ Sent</span>
      ) : (
        <span className="text-xs text-status-offline" title={pingStates[device.id]?.result?.error}>
          ❌ Failed
        </span>
      )
    }
    
    return null
  }

  if (devices.length === 0) {
    return (
      <div className="rounded-xl border-2 border-dashed border-border bg-card p-12 text-center">
        <Smartphone className="mx-auto mb-4 h-12 w-12 text-muted-foreground" />
        <h3 className="mb-2 text-lg font-semibold">No devices enrolled yet</h3>
        <p className="mb-6 text-sm text-muted-foreground">Get started by enrolling your first device</p>
        <Button onClick={onOpenSettings}>Open Settings</Button>
      </div>
    )
  }

  const getStatusColor = (device: Device) => {
    if (device.status === "offline") return "bg-status-offline"
    if (!device.last_status) return "bg-muted-foreground"
    
    const battery = device.last_status.battery?.pct || 100
    const monitoredApp = device.monitored_package ? device.last_status.app_versions?.[device.monitored_package] : null
    const monitoredAppInstalled = monitoredApp?.installed || false
    
    // Only check running status for Speedtest (other apps don't send running signals)
    const isSpeedtest = device.monitored_package === 'org.zwanoo.android.speedtest'
    const monitoredAppRunning = isSpeedtest 
      ? (device.last_status.speedtest_running_signals?.has_service_notification || false)
      : true // Default to "running" for non-Speedtest apps since we can't detect status
    
    if (battery < 20 || !monitoredAppInstalled || !monitoredAppRunning) return "bg-status-warning"
    return "bg-status-online"
  }

  const isRecentlyEnrolled = (device: Device) => {
    if (!device.created_at) return false
    const enrolledTime = new Date(device.created_at).getTime()
    const now = Date.now()
    const fiveMinutesMs = 5 * 60 * 1000
    return (now - enrolledTime) < fiveMinutesMs
  }

  return (
    <div className="overflow-hidden rounded-xl bg-card shadow-sm">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="border-b border-border bg-muted/50">
            <tr>
              {onToggleAll && (
                <th className="px-4 py-3 text-center">
                  <input
                    type="checkbox"
                    checked={selectedDeviceIds.size === devices.length && devices.length > 0}
                    onChange={onToggleAll}
                    className="h-4 w-4 rounded border-gray-300 text-primary focus:ring-2 focus:ring-primary"
                  />
                </th>
              )}
              <th className="px-4 py-3 text-left text-sm font-medium text-foreground">Status</th>
              <th className="px-4 py-3 text-left text-sm font-medium text-foreground">Alias</th>
              <th className="px-4 py-3 text-left text-sm font-medium text-foreground">Version</th>
              <th className="px-4 py-3 text-left text-sm font-medium text-foreground">Last Seen</th>
              <th className="px-4 py-3 text-right text-sm font-medium text-foreground">Battery</th>
              <th className="px-4 py-3 text-left text-sm font-medium text-foreground">Network</th>
              <th className="px-4 py-3 text-left text-sm font-medium text-foreground">Unity</th>
              <th className="hidden px-4 py-3 text-right text-sm font-medium text-foreground md:table-cell">RAM</th>
              <th className="px-4 py-3 text-right text-sm font-medium text-foreground">Uptime</th>
              <th className="px-4 py-3 text-center text-sm font-medium text-foreground">Actions</th>
            </tr>
          </thead>
          <tbody>
            {devices.map((device, index) => {
              const battery = device.last_status?.battery?.pct ?? 0
              const charging = device.last_status?.battery?.charging ?? false
              const networkTransport = device.last_status?.network?.transport || 'none'
              const network = networkTransport === 'wifi' 
                ? device.last_status?.network?.ssid || 'WiFi'
                : networkTransport === 'cell'
                ? device.last_status?.network?.carrier || 'Cellular'
                : '-'
              const monitoredApp = device.monitored_package ? device.last_status?.app_versions?.[device.monitored_package] : null
              const monitoredAppVersion = monitoredApp?.version_name || '-'
              
              const isSpeedtest = device.monitored_package === 'org.zwanoo.android.speedtest'
              const monitoredAppRunning = isSpeedtest 
                ? (device.last_status?.speedtest_running_signals?.has_service_notification ?? false)
                : null
              const ram = device.last_status?.memory?.pressure_pct ?? 0
              const uptime = device.last_status?.system?.uptime_seconds 
                ? `${Math.floor(device.last_status.system.uptime_seconds / 3600)}h`
                : '-'
              const lastSeen = formatTimestampCST(device.last_seen, { addSuffix: false })

              return (
                <tr
                  key={device.id}
                  onClick={() => onSelectDevice(device)}
                  className={`cursor-pointer transition-colors hover:bg-muted/30 ${
                    index % 2 === 0 ? "bg-background" : "bg-muted/10"
                  }`}
                >
                  {onToggleDevice && (
                    <td className="px-4 py-3 text-center" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selectedDeviceIds.has(device.id)}
                        onChange={() => onToggleDevice(device.id)}
                        className="h-4 w-4 rounded border-gray-300 text-primary focus:ring-2 focus:ring-primary"
                      />
                    </td>
                  )}
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className={`h-2 w-2 rounded-full transition-colors ${getStatusColor(device)}`} />
                      <span className="text-sm capitalize">{device.status}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium">{device.alias}</span>
                      {isRecentlyEnrolled(device) && (
                        <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-600 dark:text-emerald-400">
                          New
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-sm font-mono text-muted-foreground">{device.app_version || '-'}</span>
                  </td>
                  <td className="px-4 py-3 text-sm text-muted-foreground">{lastSeen}</td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-1.5">
                      <span className={`text-sm ${battery < 20 ? "text-status-offline" : ""}`}>
                        {battery}%
                      </span>
                      {charging && <Battery className="h-3.5 w-3.5 text-status-online" />}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5">
                      {networkTransport === 'wifi' ? (
                        <Wifi className="h-3.5 w-3.5 text-muted-foreground" />
                      ) : networkTransport === 'cell' ? (
                        <Signal className="h-3.5 w-3.5 text-muted-foreground" />
                      ) : null}
                      <span className="text-sm">{network}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span className="text-sm">{monitoredAppVersion}</span>
                      {monitoredAppRunning !== null ? (
                        <span
                          className={`rounded-full px-2 py-0.5 text-xs ${
                            monitoredAppRunning
                              ? "bg-status-online/10 text-status-online"
                              : "bg-status-offline/10 text-status-offline"
                          }`}
                        >
                          {monitoredAppRunning ? "Running" : "Down"}
                        </span>
                      ) : (
                        <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                          N/A
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="hidden px-4 py-3 text-right text-sm md:table-cell">{ram}%</td>
                  <td className="px-4 py-3 text-right text-sm text-muted-foreground">{uptime}</td>
                  <td className="px-4 py-3 text-center" onClick={(e) => e.stopPropagation()}>
                    <div className="flex items-center justify-center gap-1">
                      {getPingStatusDisplay(device) || (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={(e) => handlePing(e, device.id)}
                          className="h-7 px-2 text-xs"
                        >
                          <Radio className="h-3.5 w-3.5 mr-1" />
                          Ping
                        </Button>
                      )}
                      {ringStates[device.id]?.loading ? (
                        <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                          <Bell className="h-3.5 w-3.5 animate-pulse" />
                          Ringing...
                        </span>
                      ) : ringStates[device.id]?.result ? (
                        ringStates[device.id]?.result?.ok ? (
                          <span className="text-xs text-status-online">🔔 Sent</span>
                        ) : (
                          <span className="text-xs text-status-offline" title={ringStates[device.id]?.result?.error}>
                            ❌ Failed
                          </span>
                        )
                      ) : (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={(e) => handleRing(e, device.id)}
                          className="h-7 px-2 text-xs"
                        >
                          <Bell className="h-3.5 w-3.5 mr-1" />
                          Ring
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
