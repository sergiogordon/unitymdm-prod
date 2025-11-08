"use client"

import { Battery, Wifi, Smartphone, Search, Settings2, Bell, BellOff, Radio } from "lucide-react"
import type { Device } from "@/lib/mock-data"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { BulkActionsBar } from "@/components/bulk-actions-bar"
import { BulkDeleteModal } from "@/components/bulk-delete-modal"
import { DeviceMonitoringModal } from "@/components/device-monitoring-modal"
import { useToast } from "@/hooks/use-toast"
import { bulkDeleteDevices, pingDevice, ringDevice, stopRingingDevice } from "@/lib/api-client"

interface Pagination {
  page: number
  limit: number
  total_count: number
  total_pages: number
  has_next: boolean
  has_prev: boolean
}

interface DevicesTableProps {
  devices: Device[]
  onSelectDevice: (device: Device) => void
  onDevicesDeleted?: () => void
  pagination?: Pagination | null
  currentPage?: number
  pageSize?: number
  onNextPage?: () => void
  onPrevPage?: () => void
  onChangePageSize?: (size: number) => void
}

export function DevicesTable({ devices, onSelectDevice, onDevicesDeleted, pagination, currentPage = 1, pageSize = 25, onNextPage, onPrevPage, onChangePageSize }: DevicesTableProps) {
  const router = useRouter()
  const [searchQuery, setSearchQuery] = useState("")
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false)
  const [monitoringDevice, setMonitoringDevice] = useState<Device | null>(null)
  const [pingLoading, setPingLoading] = useState<Set<string>>(new Set())
  const [ringLoading, setRingLoading] = useState<Set<string>>(new Set())
  const { toast } = useToast()

  const filteredDevices = devices.filter((device) => {
    const query = searchQuery.toLowerCase()
    
    if (query === "service:down" || query === "service-down") {
      return device.monitoring?.service_up === false
    }
    
    if (query === "service:up" || query === "service-up") {
      return device.monitoring?.service_up === true
    }
    
    if (query === "service:unknown" || query === "service-unknown") {
      return device.monitoring?.service_up === null || !device.monitoring
    }
    
    return (
      device.alias.toLowerCase().includes(query) ||
      device.status.toLowerCase().includes(query) ||
      device.network.name.toLowerCase().includes(query) ||
      (device.unity.version?.toLowerCase().includes(query) ?? false) ||
      device.unity.status.toLowerCase().includes(query) ||
      (device.monitoring?.monitored_app_name?.toLowerCase().includes(query) ?? false) ||
      (device.monitoring?.monitored_package?.toLowerCase().includes(query) ?? false)
    )
  })

  // Clear selection when filtered devices change
  useEffect(() => {
    const validIds = new Set(filteredDevices.map(d => d.id))
    setSelectedIds(prev => {
      const newSelected = new Set([...prev].filter(id => validIds.has(id)))
      return newSelected.size === prev.size ? prev : newSelected
    })
  }, [filteredDevices])

  const toggleSelectAll = () => {
    if (selectedIds.size === filteredDevices.length && filteredDevices.length > 0) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(filteredDevices.map(d => d.id)))
    }
  }

  const toggleSelectDevice = (deviceId: string) => {
    setSelectedIds(prev => {
      const newSet = new Set(prev)
      if (newSet.has(deviceId)) {
        newSet.delete(deviceId)
      } else {
        newSet.add(deviceId)
      }
      return newSet
    })
  }

  const handleBulkDelete = async (purgeHistory: boolean) => {
    const deviceIdsArray = Array.from(selectedIds)
    
    try {
      const result = await bulkDeleteDevices(deviceIdsArray, purgeHistory)
      
      toast({
        title: "Devices deleted",
        description: `Successfully deleted ${result.deleted} device(s)${result.skipped > 0 ? `, skipped ${result.skipped}` : ''}`,
        variant: "default"
      })
      
      setSelectedIds(new Set())
      onDevicesDeleted?.()
    } catch (error) {
      toast({
        title: "Delete failed",
        description: error instanceof Error ? error.message : "Failed to delete devices",
        variant: "destructive"
      })
      throw error
    }
  }

  const handlePing = async (deviceId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setPingLoading(prev => new Set([...prev, deviceId]))
    
    try {
      await pingDevice(deviceId)
      toast({
        title: "Ping sent",
        description: "Device will respond with telemetry data",
        variant: "default"
      })
    } catch (error) {
      toast({
        title: "Ping failed",
        description: error instanceof Error ? error.message : "Failed to ping device",
        variant: "destructive"
      })
    } finally {
      setPingLoading(prev => {
        const newSet = new Set(prev)
        newSet.delete(deviceId)
        return newSet
      })
    }
  }

  const handleRing = async (deviceId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setRingLoading(prev => new Set([...prev, deviceId]))
    
    try {
      await ringDevice(deviceId, 30, 1.0)
      toast({
        title: "Ring command sent",
        description: "Device will ring for 30 seconds",
        variant: "default"
      })
      // Refresh device list to show updated ringing status
      onDevicesDeleted?.()
    } catch (error) {
      toast({
        title: "Ring failed",
        description: error instanceof Error ? error.message : "Failed to ring device",
        variant: "destructive"
      })
    } finally {
      setRingLoading(prev => {
        const newSet = new Set(prev)
        newSet.delete(deviceId)
        return newSet
      })
    }
  }

  const handleStopRing = async (deviceId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setRingLoading(prev => new Set([...prev, deviceId]))
    
    try {
      await stopRingingDevice(deviceId)
      toast({
        title: "Stop ring sent",
        description: "Device will stop ringing",
        variant: "default"
      })
      onDevicesDeleted?.()
    } catch (error) {
      toast({
        title: "Stop ring failed",
        description: error instanceof Error ? error.message : "Failed to stop ring",
        variant: "destructive"
      })
    } finally {
      setRingLoading(prev => {
        const newSet = new Set(prev)
        newSet.delete(deviceId)
        return newSet
      })
    }
  }

  const selectedDevices = devices.filter(d => selectedIds.has(d.id))
  const sampleAliases = selectedDevices.slice(0, 10).map(d => d.alias)

  const allSelectedOnPage = filteredDevices.length > 0 && filteredDevices.every(d => selectedIds.has(d.id))
  const someSelectedOnPage = filteredDevices.some(d => selectedIds.has(d.id)) && !allSelectedOnPage

  if (devices.length === 0) {
    return (
      <div className="rounded-xl border-2 border-dashed border-border bg-card p-12 text-center">
        <Smartphone className="mx-auto mb-4 h-12 w-12 text-muted-foreground" />
        <h3 className="mb-2 text-lg font-semibold">No devices enrolled yet</h3>
        <p className="mb-6 text-sm text-muted-foreground">Get started by enrolling your first device</p>
        <Button onClick={() => router.push('/adb-setup')}>Enroll Devices</Button>
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
                <th className="w-12 px-4 py-3">
                  <Checkbox
                    checked={allSelectedOnPage}
                    onCheckedChange={toggleSelectAll}
                    aria-label="Select all devices on this page"
                    className={someSelectedOnPage ? "data-[state=checked]:bg-primary/50" : ""}
                  />
                </th>
                <th className="px-4 py-3 text-left text-sm font-medium">Status</th>
                <th className="px-4 py-3 text-left text-sm font-medium">Alias</th>
                <th className="px-4 py-3 text-left text-sm font-medium">Service</th>
                <th className="px-4 py-3 text-left text-sm font-medium">Last Seen</th>
                <th className="px-4 py-3 text-left text-sm font-medium">Actions</th>
                <th className="px-4 py-3 text-right text-sm font-medium">Battery</th>
                <th className="px-4 py-3 text-left text-sm font-medium">Network</th>
                <th className="px-4 py-3 text-left text-sm font-medium">Agent</th>
                <th className="hidden px-4 py-3 text-right text-sm font-medium md:table-cell">RAM</th>
                <th className="px-4 py-3 text-right text-sm font-medium">Uptime</th>
                <th className="w-12 px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {filteredDevices.length === 0 ? (
                <tr>
                  <td colSpan={12} className="px-4 py-12 text-center">
                    <p className="text-sm text-muted-foreground">No devices found matching "{searchQuery}"</p>
                  </td>
                </tr>
              ) : (
                filteredDevices.map((device, index) => {
                  const serviceStatus = device.monitoring?.service_up === true ? "Up" :
                                       device.monitoring?.service_up === false ? "Down" :
                                       "Unknown"
                  const lastForegroundMin = device.monitoring?.monitored_foreground_recent_s != null
                    ? Math.floor(device.monitoring.monitored_foreground_recent_s / 60)
                    : null
                    
                  return (
                    <tr
                      key={device.id}
                      className={`transition-colors hover:bg-muted/30 ${
                        index % 2 === 0 ? "bg-background" : "bg-muted/10"
                      } ${selectedIds.has(device.id) ? "bg-primary/5" : ""}`}
                    >
                      <td className="px-4 py-3">
                        <Checkbox
                          checked={selectedIds.has(device.id)}
                          onCheckedChange={() => toggleSelectDevice(device.id)}
                          onClick={(e) => e.stopPropagation()}
                          aria-label={`Select ${device.alias}`}
                        />
                      </td>
                      <td className="px-4 py-3 cursor-pointer" onClick={() => onSelectDevice(device)}>
                        <div className="flex items-center gap-2">
                          <div
                            className={`h-2 w-2 rounded-full ${
                              device.status === "online" ? "bg-status-online" : "bg-status-offline"
                            }`}
                          />
                          <span className="text-sm capitalize">{device.status}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-sm font-medium cursor-pointer" onClick={() => onSelectDevice(device)}>{device.alias}</td>
                      <td className="px-4 py-3 cursor-pointer" onClick={() => onSelectDevice(device)}>
                        {device.monitoring ? (
                          <div className="flex items-center gap-2">
                            <span className="text-sm">{device.monitoring.monitored_app_name || device.monitoring.monitored_package}</span>
                            <span
                              className={`rounded-full px-2 py-0.5 text-xs ${
                                serviceStatus === "Up"
                                  ? "bg-status-online/10 text-status-online"
                                  : serviceStatus === "Down"
                                  ? "bg-status-offline/10 text-status-offline"
                                  : "bg-muted text-muted-foreground"
                              }`}
                            >
                              {serviceStatus}
                            </span>
                            {lastForegroundMin != null && (
                              <span className="text-xs text-muted-foreground">
                                {lastForegroundMin}m
                              </span>
                            )}
                          </div>
                        ) : (
                          <span className="text-xs text-muted-foreground">Not configured</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm text-muted-foreground cursor-pointer" onClick={() => onSelectDevice(device)}>{device.lastSeen}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1">
                          {device.ringing_until && new Date(device.ringing_until) > new Date() ? (
                            <>
                              <span className="flex items-center gap-1 rounded-full bg-orange-500/10 px-2 py-1 text-xs text-orange-600">
                                <Bell className="h-3 w-3" />
                                Ringing...
                              </span>
                              <Button
                                variant="ghost"
                                size="icon"
                                onClick={(e) => handleStopRing(device.id, e)}
                                disabled={ringLoading.has(device.id)}
                                className="h-7 w-7"
                                title="Stop ringing"
                              >
                                <BellOff className="h-3.5 w-3.5" />
                              </Button>
                            </>
                          ) : (
                            <>
                              <Button
                                variant="ghost"
                                size="icon"
                                onClick={(e) => handlePing(device.id, e)}
                                disabled={pingLoading.has(device.id) || device.status === 'offline'}
                                className="h-7 w-7"
                                title="Ping device (request heartbeat)"
                              >
                                <Radio className="h-3.5 w-3.5" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="icon"
                                onClick={(e) => handleRing(device.id, e)}
                                disabled={ringLoading.has(device.id) || device.status === 'offline'}
                                className="h-7 w-7"
                                title="Ring + Flashlight to locate"
                              >
                                <Bell className="h-3.5 w-3.5" />
                              </Button>
                            </>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-right cursor-pointer" onClick={() => onSelectDevice(device)}>
                        <div className="flex items-center justify-end gap-1.5">
                          <span className={`text-sm ${device.battery.percentage < 20 ? "text-status-offline" : ""}`}>
                            {device.battery.percentage}%
                          </span>
                          {device.battery.charging && <Battery className="h-3.5 w-3.5 text-status-online" />}
                        </div>
                      </td>
                      <td className="px-4 py-3 cursor-pointer" onClick={() => onSelectDevice(device)}>
                        <div className="flex items-center gap-1.5">
                          <Wifi className="h-3.5 w-3.5 text-muted-foreground" />
                          <span className="text-sm">{device.network.name}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 cursor-pointer" onClick={() => onSelectDevice(device)}>
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
                      <td className="hidden px-4 py-3 text-right text-sm md:table-cell cursor-pointer" onClick={() => onSelectDevice(device)}>{device.ram}%</td>
                      <td className="px-4 py-3 text-right text-sm text-muted-foreground cursor-pointer" onClick={() => onSelectDevice(device)}>{device.uptime}</td>
                      <td className="px-4 py-3">
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={(e) => {
                            e.stopPropagation()
                            setMonitoringDevice(device)
                          }}
                          className="h-8 w-8"
                        >
                          <Settings2 className="h-4 w-4" />
                        </Button>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination Controls */}
      {pagination && (
        <div className="mt-4 flex items-center justify-between px-4 py-3 bg-card rounded-lg border border-border">
          <div className="flex items-center gap-4">
            <div className="text-sm text-muted-foreground">
              Showing <span className="font-medium text-foreground">{((currentPage - 1) * pageSize) + 1}</span> to{" "}
              <span className="font-medium text-foreground">{Math.min(currentPage * pageSize, pagination.total_count)}</span> of{" "}
              <span className="font-medium text-foreground">{pagination.total_count}</span> devices
            </div>
            
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">Devices per page:</span>
              <select
                value={pageSize}
                onChange={(e) => onChangePageSize?.(Number(e.target.value))}
                className="rounded border border-border bg-background px-2 py-1 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
              >
                <option value={25}>25</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={onPrevPage}
              disabled={!pagination.has_prev}
            >
              Previous
            </Button>
            
            <div className="px-3 py-1 text-sm">
              Page <span className="font-medium">{currentPage}</span> of <span className="font-medium">{pagination.total_pages}</span>
            </div>
            
            <Button
              variant="outline"
              size="sm"
              onClick={onNextPage}
              disabled={!pagination.has_next}
            >
              Next
            </Button>
          </div>
        </div>
      )}

      <BulkActionsBar
        selectedCount={selectedIds.size}
        onDelete={() => setIsDeleteModalOpen(true)}
        onClear={() => setSelectedIds(new Set())}
      />

      <BulkDeleteModal
        isOpen={isDeleteModalOpen}
        onClose={() => setIsDeleteModalOpen(false)}
        onConfirm={handleBulkDelete}
        deviceCount={selectedIds.size}
        sampleAliases={sampleAliases}
      />
      
      {monitoringDevice && (
        <DeviceMonitoringModal
          isOpen={true}
          onClose={() => setMonitoringDevice(null)}
          deviceId={monitoringDevice.id}
          deviceAlias={monitoringDevice.alias}
          currentMonitoring={monitoringDevice.monitoring}
          onUpdated={() => {
            onDevicesDeleted?.()
          }}
        />
      )}
    </div>
  )
}
