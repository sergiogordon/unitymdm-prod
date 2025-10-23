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
                <span className="text-sm font-medium">{device.lastSeen}</span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Battery</span>
                <span className="text-sm font-medium">
                  {device.battery.percentage}%{device.battery.charging && " (Charging)"}
                </span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Network</span>
                <span className="text-sm font-medium">
                  {device.network.type} • {device.network.name}
                </span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Agent</span>
                <span className="text-sm font-medium">
                  {device.unity.version} ({device.unity.status})
                </span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Uptime</span>
                <span className="text-sm font-medium">{device.uptime}</span>
              </div>
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
