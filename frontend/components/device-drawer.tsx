"use client"

import { useEffect, useState } from "react"
import { X, Pencil, Check } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useToast } from "@/hooks/use-toast"
import type { Device } from "@/lib/mock-data"

interface DeviceDrawerProps {
  device: Device | null
  isOpen: boolean
  onClose: () => void
  onDeviceUpdated?: () => void
}

export function DeviceDrawer({ device, isOpen, onClose, onDeviceUpdated }: DeviceDrawerProps) {
  const { toast } = useToast()
  const [isEditing, setIsEditing] = useState(false)
  const [editedAlias, setEditedAlias] = useState("")
  const [isSaving, setIsSaving] = useState(false)

  // Reset edit state when device changes or drawer closes
  useEffect(() => {
    if (device) {
      setEditedAlias(device.alias)
      setIsEditing(false)
    }
  }, [device?.id])

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (isEditing) {
          setEditedAlias(device?.alias || "")
          setIsEditing(false)
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
  }, [isOpen, onClose, isEditing, device?.alias])

  const handleStartEdit = () => {
    setEditedAlias(device?.alias || "")
    setIsEditing(true)
  }

  const handleCancelEdit = () => {
    setEditedAlias(device?.alias || "")
    setIsEditing(false)
  }

  const handleSaveAlias = async () => {
    if (!device || !editedAlias.trim()) {
      toast({
        title: "Error",
        description: "Alias cannot be empty",
        variant: "destructive",
      })
      return
    }

    if (editedAlias.trim() === device.alias) {
      setIsEditing(false)
      return
    }

    setIsSaving(true)
    try {
      const token = localStorage.getItem('token')
      const response = await fetch(`/api/proxy/v1/devices/${device.id}/alias`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`,
        },
        body: JSON.stringify({ alias: editedAlias.trim() }),
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.error || "Failed to update alias")
      }

      toast({
        title: "Success",
        description: "Device alias updated successfully",
      })
      
      setIsEditing(false)
      
      // Notify parent to refresh the device list
      if (onDeviceUpdated) {
        onDeviceUpdated()
      }
    } catch (error) {
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to update alias",
        variant: "destructive",
      })
    } finally {
      setIsSaving(false)
    }
  }

  if (!isOpen || !device) return null

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/20 backdrop-blur-sm" onClick={onClose} />
      <div className="fixed right-0 top-0 z-50 h-full w-full max-w-[480px] animate-in slide-in-from-right">
        <div className="flex h-full flex-col bg-card shadow-2xl">
          <div className="flex items-center justify-between border-b border-border px-6 py-4">
            {isEditing ? (
              <div className="flex items-center gap-2 flex-1 mr-2">
                <Input
                  value={editedAlias}
                  onChange={(e) => setEditedAlias(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      handleSaveAlias()
                    }
                  }}
                  className="flex-1"
                  placeholder="Device alias"
                  autoFocus
                  disabled={isSaving}
                />
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={handleSaveAlias}
                  disabled={isSaving}
                  title="Save"
                >
                  <Check className="h-4 w-4 text-green-600" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={handleCancelEdit}
                  disabled={isSaving}
                  title="Cancel"
                >
                  <X className="h-4 w-4 text-red-600" />
                </Button>
              </div>
            ) : (
              <div className="flex items-center gap-2 flex-1">
                <h2 className="text-lg font-semibold">{device.alias}</h2>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={handleStartEdit}
                  className="h-7 w-7"
                  title="Edit alias"
                >
                  <Pencil className="h-3.5 w-3.5" />
                </Button>
              </div>
            )}
            {!isEditing && (
              <Button variant="ghost" size="icon" onClick={onClose}>
                <X className="h-4 w-4" />
              </Button>
            )}
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
                    <td className="px-4 py-3 text-sm text-muted-foreground font-medium">next MDM Version</td>
                    <td className="px-4 py-3 text-sm font-medium font-mono text-xs">{device.unity.version}</td>
                  </tr>
                  <tr className="hover:bg-muted/80 transition-colors">
                    <td className="px-4 py-3 text-sm text-muted-foreground font-medium">next MDM Status</td>
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
