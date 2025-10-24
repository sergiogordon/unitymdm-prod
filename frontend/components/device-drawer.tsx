"use client"

import { useEffect } from "react"
import { X } from "lucide-react"
import { Button } from "@/components/ui/button"
import type { Device } from "@/lib/mock-data"

interface DeviceDrawerProps {
  device: Device | null
  isOpen: boolean
  onClose: () => void
}

export function DeviceDrawer({ device, isOpen, onClose }: DeviceDrawerProps) {
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

  if (!isOpen || !device) return null

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/20 backdrop-blur-sm" onClick={onClose} />
      <div className="fixed right-0 top-0 z-50 h-full w-full max-w-[480px] animate-in slide-in-from-right">
        <div className="flex h-full flex-col bg-card shadow-2xl">
          <div className="flex items-center justify-between border-b border-border px-6 py-4">
            <h2 className="text-lg font-semibold">{device.alias}</h2>
            <Button variant="ghost" size="icon" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          </div>

          <div className="flex-1 overflow-y-auto p-6">
            <div className="mb-6 rounded-lg border border-border bg-muted/50 overflow-hidden">
              <table className="w-full">
                <tbody className="divide-y divide-border">
                  <tr className="hover:bg-muted/80 transition-colors">
                    <td className="px-4 py-3 text-sm text-muted-foreground font-medium w-1/3">Status</td>
                    <td className="px-4 py-3 text-sm">
                      <div className="flex items-center gap-2">
                        <div
                          className={`h-2 w-2 rounded-full ${
                            device.status === "online" ? "bg-status-online" : "bg-status-offline"
                          }`}
                        />
                        <span className="font-medium capitalize">{device.status}</span>
                      </div>
                    </td>
                  </tr>
                  <tr className="hover:bg-muted/80 transition-colors">
                    <td className="px-4 py-3 text-sm text-muted-foreground font-medium">Last Seen</td>
                    <td className="px-4 py-3 text-sm font-medium">{device.lastSeen}</td>
                  </tr>
                  <tr className="hover:bg-muted/80 transition-colors">
                    <td className="px-4 py-3 text-sm text-muted-foreground font-medium">Battery</td>
                    <td className="px-4 py-3 text-sm font-medium">
                      {device.battery.percentage}%{device.battery.charging && " (Charging)"}
                    </td>
                  </tr>
                  <tr className="hover:bg-muted/80 transition-colors">
                    <td className="px-4 py-3 text-sm text-muted-foreground font-medium">Network</td>
                    <td className="px-4 py-3 text-sm font-medium">
                      {device.network.type} • {device.network.name}
                    </td>
                  </tr>
                  <tr className="hover:bg-muted/80 transition-colors">
                    <td className="px-4 py-3 text-sm text-muted-foreground font-medium">Unity Version</td>
                    <td className="px-4 py-3 text-sm font-medium font-mono text-xs">{device.unity.version}</td>
                  </tr>
                  <tr className="hover:bg-muted/80 transition-colors">
                    <td className="px-4 py-3 text-sm text-muted-foreground font-medium">Unity Status</td>
                    <td className="px-4 py-3 text-sm font-medium capitalize">{device.unity.status}</td>
                  </tr>
                  {device.monitoring?.monitor_enabled && device.monitoring.monitored_app_name && (
                    <tr className="hover:bg-muted/80 transition-colors">
                      <td className="px-4 py-3 text-sm text-muted-foreground font-medium">Monitored Service</td>
                      <td className="px-4 py-3 text-sm">
                        <div className="flex items-center gap-2">
                          <span className="font-medium">{device.monitoring.monitored_app_name}</span>
                          {device.monitoring.service_up !== null && (
                            <span className={`text-xs px-2 py-0.5 rounded-full ${
                              device.monitoring.service_up 
                                ? "bg-green-500/10 text-green-500" 
                                : "bg-red-500/10 text-red-500"
                            }`}>
                              {device.monitoring.service_up ? "Running" : "Down"}
                            </span>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                  <tr className="hover:bg-muted/80 transition-colors">
                    <td className="px-4 py-3 text-sm text-muted-foreground font-medium">RAM Usage</td>
                    <td className="px-4 py-3 text-sm font-medium">{device.ram}%</td>
                  </tr>
                  <tr className="hover:bg-muted/80 transition-colors">
                    <td className="px-4 py-3 text-sm text-muted-foreground font-medium">Uptime</td>
                    <td className="px-4 py-3 text-sm font-medium">{device.uptime}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div>
              <h3 className="mb-3 text-sm font-medium">Device Details</h3>
              <pre className="overflow-x-auto rounded-lg bg-muted p-4 text-xs font-mono">
                {JSON.stringify(
                  {
                    id: device.id,
                    alias: device.alias,
                    status: device.status,
                    lastSeen: device.lastSeen,
                    battery: device.battery,
                    network: device.network,
                    unity: device.unity,
                    ram: device.ram,
                    uptime: device.uptime,
                  },
                  null,
                  2,
                )}
              </pre>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
