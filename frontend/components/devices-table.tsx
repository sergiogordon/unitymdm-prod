"use client"

import { Battery, Wifi, Smartphone, Search } from "lucide-react"
import type { Device } from "@/lib/mock-data"
import { Button } from "@/components/ui/button"
import { useState } from "react"

interface DevicesTableProps {
  devices: Device[]
  onSelectDevice: (device: Device) => void
}

export function DevicesTable({ devices, onSelectDevice }: DevicesTableProps) {
  const [searchQuery, setSearchQuery] = useState("")

  const filteredDevices = devices.filter((device) => {
    const query = searchQuery.toLowerCase()
    return (
      device.alias.toLowerCase().includes(query) ||
      device.status.toLowerCase().includes(query) ||
      device.network.name.toLowerCase().includes(query) ||
      device.unity.version.toLowerCase().includes(query) ||
      device.unity.status.toLowerCase().includes(query)
    )
  })

  if (devices.length === 0) {
    return (
      <div className="rounded-xl border-2 border-dashed border-border bg-card p-12 text-center">
        <Smartphone className="mx-auto mb-4 h-12 w-12 text-muted-foreground" />
        <h3 className="mb-2 text-lg font-semibold">No devices enrolled yet</h3>
        <p className="mb-6 text-sm text-muted-foreground">Get started by enrolling your first device</p>
        <Button>Open Settings</Button>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          type="text"
          placeholder="Search devices by alias, status, network..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full rounded-lg border border-border bg-card px-10 py-2.5 text-sm outline-none transition-colors placeholder:text-muted-foreground focus:border-primary focus:ring-2 focus:ring-primary/20"
        />
        {searchQuery && (
          <button
            onClick={() => setSearchQuery("")}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        )}
      </div>

      <div className="overflow-hidden rounded-xl bg-card shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="border-b border-border bg-muted/50">
              <tr>
                <th className="px-4 py-3 text-left text-sm font-medium">Status</th>
                <th className="px-4 py-3 text-left text-sm font-medium">Alias</th>
                <th className="px-4 py-3 text-left text-sm font-medium">Last Seen</th>
                <th className="px-4 py-3 text-right text-sm font-medium">Battery</th>
                <th className="px-4 py-3 text-left text-sm font-medium">Network</th>
                <th className="px-4 py-3 text-left text-sm font-medium">Unity</th>
                <th className="hidden px-4 py-3 text-right text-sm font-medium md:table-cell">RAM</th>
                <th className="px-4 py-3 text-right text-sm font-medium">Uptime</th>
              </tr>
            </thead>
            <tbody>
              {filteredDevices.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-12 text-center">
                    <p className="text-sm text-muted-foreground">No devices found matching "{searchQuery}"</p>
                  </td>
                </tr>
              ) : (
                filteredDevices.map((device, index) => (
                  <tr
                    key={device.id}
                    onClick={() => onSelectDevice(device)}
                    className={`cursor-pointer transition-colors hover:bg-muted/30 ${
                      index % 2 === 0 ? "bg-background" : "bg-muted/10"
                    }`}
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div
                          className={`h-2 w-2 rounded-full ${
                            device.status === "online" ? "bg-status-online" : "bg-status-offline"
                          }`}
                        />
                        <span className="text-sm capitalize">{device.status}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-sm font-medium">{device.alias}</td>
                    <td className="px-4 py-3 text-sm text-muted-foreground">{device.lastSeen}</td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <span className={`text-sm ${device.battery.percentage < 20 ? "text-status-offline" : ""}`}>
                          {device.battery.percentage}%
                        </span>
                        {device.battery.charging && <Battery className="h-3.5 w-3.5 text-status-online" />}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5">
                        <Wifi className="h-3.5 w-3.5 text-muted-foreground" />
                        <span className="text-sm">{device.network.name}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="text-sm">{device.unity.version}</span>
                        <span
                          className={`rounded-full px-2 py-0.5 text-xs ${
                            device.unity.status === "running"
                              ? "bg-status-online/10 text-status-online"
                              : "bg-status-offline/10 text-status-offline"
                          }`}
                        >
                          {device.unity.status}
                        </span>
                      </div>
                    </td>
                    <td className="hidden px-4 py-3 text-right text-sm md:table-cell">{device.ram}%</td>
                    <td className="px-4 py-3 text-right text-sm text-muted-foreground">{device.uptime}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
