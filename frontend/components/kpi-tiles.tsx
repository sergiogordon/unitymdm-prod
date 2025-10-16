"use client"

import { useState } from "react"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { AlertTriangle, Battery, WifiOff, XCircle } from "lucide-react"
import type { Device } from "@/lib/mock-data"

interface KpiTilesProps {
  total: number
  online: number
  offline: number
  alerts: number
  devices: Device[]
}

export function KpiTiles({ total, online, offline, alerts, devices }: KpiTilesProps) {
  const [showAlertsDialog, setShowAlertsDialog] = useState(false)

  const alertedDevices = devices.filter(
    (d) => d.status === "offline" || d.unity.status === "down" || d.battery.percentage < 20,
  )

  const getAlertReasons = (device: Device) => {
    const reasons = []
    if (device.status === "offline") reasons.push("Offline")
    if (device.unity.status === "down") reasons.push("Unity Down")
    if (device.battery.percentage < 20) reasons.push("Low Battery")
    return reasons
  }

  return (
    <>
      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl bg-card p-6 shadow-sm">
          <div className="text-3xl font-semibold tracking-tight">{total}</div>
          <div className="mt-1 text-sm text-muted-foreground">Total Devices</div>
        </div>

        <div className="rounded-xl bg-card p-6 shadow-sm">
          <div className="text-3xl font-semibold tracking-tight text-status-online">{online}</div>
          <div className="mt-1 text-sm text-muted-foreground">Online</div>
        </div>

        <div className="rounded-xl bg-card p-6 shadow-sm">
          <div className={`text-3xl font-semibold tracking-tight ${offline > 0 ? "text-status-offline" : ""}`}>
            {offline}
          </div>
          <div className="mt-1 text-sm text-muted-foreground">Offline</div>
        </div>

        <button
          onClick={() => setShowAlertsDialog(true)}
          className="rounded-xl bg-card p-6 shadow-sm text-left transition-all hover:shadow-md hover:scale-[1.02] active:scale-[0.98] disabled:pointer-events-none"
          disabled={alerts === 0}
        >
          <div className={`text-3xl font-semibold tracking-tight ${alerts > 0 ? "text-status-warning" : ""}`}>
            {alerts}
          </div>
          <div className="mt-1 text-sm text-muted-foreground">Active Alerts</div>
        </button>
      </div>

      <Dialog open={showAlertsDialog} onOpenChange={setShowAlertsDialog}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-status-warning" />
              Active Alerts ({alertedDevices.length})
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-3 mt-4">
            {alertedDevices.map((device) => {
              const reasons = getAlertReasons(device)
              return (
                <div
                  key={device.id}
                  className="rounded-lg border border-border bg-card p-4 hover:bg-accent/50 transition-colors"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        <h3 className="font-semibold text-base">{device.alias}</h3>
                        <span
                          className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${
                            device.status === "online"
                              ? "bg-status-online/10 text-status-online"
                              : "bg-status-offline/10 text-status-offline"
                          }`}
                        >
                          <span
                            className={`h-1.5 w-1.5 rounded-full ${
                              device.status === "online" ? "bg-status-online" : "bg-status-offline"
                            }`}
                          />
                          {device.status}
                        </span>
                      </div>

                      <div className="flex flex-wrap gap-2 mb-3">
                        {reasons.map((reason) => (
                          <span
                            key={reason}
                            className="inline-flex items-center gap-1 rounded-md bg-status-warning/10 px-2 py-1 text-xs font-medium text-status-warning"
                          >
                            {reason === "Offline" && <WifiOff className="h-3 w-3" />}
                            {reason === "Unity Down" && <XCircle className="h-3 w-3" />}
                            {reason === "Low Battery" && <Battery className="h-3 w-3" />}
                            {reason}
                          </span>
                        ))}
                      </div>

                      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                        <div className="text-muted-foreground">Last Seen:</div>
                        <div className="font-mono">{device.lastSeen}</div>

                        <div className="text-muted-foreground">Battery:</div>
                        <div
                          className={`font-mono ${device.battery.percentage < 20 ? "text-status-warning font-semibold" : ""}`}
                        >
                          {device.battery.percentage}%{device.battery.charging && " (Charging)"}
                        </div>

                        <div className="text-muted-foreground">Unity:</div>
                        <div
                          className={`font-mono ${device.unity.status === "down" ? "text-status-offline font-semibold" : ""}`}
                        >
                          {device.unity.version} - {device.unity.status}
                        </div>

                        <div className="text-muted-foreground">Network:</div>
                        <div className="font-mono">{device.network.name}</div>
                      </div>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>

          <div className="mt-4 flex justify-end">
            <Button onClick={() => setShowAlertsDialog(false)} variant="outline">
              Close
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
