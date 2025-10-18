"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { Search, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Header } from "@/components/header"
import { Sidebar } from "@/components/sidebar"
import { KpiTiles } from "@/components/kpi-tiles"
import { FilterBar } from "@/components/filter-bar"
import { DevicesTable } from "@/components/devices-table"
import { DeviceDrawer } from "@/components/device-drawer"
import { SettingsDrawer } from "@/components/settings-drawer"
import { AlertsDialog } from "@/components/alerts-dialog"
import { ProtectedLayout } from "@/components/protected-layout"
import { fetchDevices, fetchMetrics, filterDevices, type Device, type FilterType, type PaginatedDevicesResponse, type MetricsResponse } from "@/lib/api"
import { useWebSocket } from "@/lib/websocket"

export default function Page() {
  return (
    <ProtectedLayout>
      <DashboardContent />
    </ProtectedLayout>
  )
}

function DashboardContent() {
  const router = useRouter()
  const [isDark, setIsDark] = useState(false)
  const [isSidebarOpen, setIsSidebarOpen] = useState(true)
  const [lastUpdated, setLastUpdated] = useState(Date.now())
  const [selectedFilter, setSelectedFilter] = useState<FilterType>("all")
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null)
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  const [isAlertsDialogOpen, setIsAlertsDialogOpen] = useState(false)
  const [devices, setDevices] = useState<Device[]>([])
  const [pagination, setPagination] = useState<PaginatedDevicesResponse["pagination"]>({
    page: 1,
    limit: 25,
    total_count: 0,
    total_pages: 0,
    has_next: false,
    has_prev: false
  })
  const [currentPage, setCurrentPage] = useState(1)
  const [metrics, setMetrics] = useState<MetricsResponse>({ total: 0, online: 0, offline: 0, low_battery: 0 })
  const [refreshInterval, setRefreshInterval] = useState(120000)
  const [previousDeviceCount, setPreviousDeviceCount] = useState(0)
  const [hasLoaded, setHasLoaded] = useState(false)
  const [searchQuery, setSearchQuery] = useState("")
  const [selectedDeviceIds, setSelectedDeviceIds] = useState<Set<string>>(new Set())
  const [isDeletingBulk, setIsDeletingBulk] = useState(false)

  // Toggle dark mode
  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add("dark")
    } else {
      document.documentElement.classList.remove("dark")
    }
  }, [isDark])

  // Load dark mode preference
  useEffect(() => {
    const isDarkMode = localStorage.getItem('darkMode') === 'true'
    setIsDark(isDarkMode)
  }, [])

  // Load sidebar preference
  useEffect(() => {
    const sidebarOpen = localStorage.getItem('sidebarOpen')
    if (sidebarOpen !== null) {
      setIsSidebarOpen(sidebarOpen === 'true')
    }
  }, [])

  // Load refresh interval preference
  useEffect(() => {
    const interval = localStorage.getItem('refreshInterval')
    if (interval) setRefreshInterval(parseInt(interval) * 1000)
  }, [])

  // Fetch devices and metrics
  const loadDevices = async (page = currentPage) => {
    const response = await fetchDevices(page, 25)
    setDevices(response.devices)
    setPagination(response.pagination)
    setLastUpdated(Date.now())
  }

  const loadMetrics = async () => {
    const metricsData = await fetchMetrics()
    setMetrics(metricsData)
    
    // Check for newly enrolled devices
    if (hasLoaded && metricsData.total > previousDeviceCount) {
      const newDeviceCount = metricsData.total - previousDeviceCount
      toast.success(`${newDeviceCount} new device${newDeviceCount > 1 ? 's' : ''} enrolled!`, {
        duration: 5000,
      })
    }
    setPreviousDeviceCount(metricsData.total)
  }

  // WebSocket message handler
  const handleWebSocketMessage = async (data: any) => {
    if (data.type === "device_update") {
      await loadDevices(currentPage)
      await loadMetrics()
    }
  }

  // Initialize WebSocket
  useWebSocket(handleWebSocketMessage)

  // Initial load
  useEffect(() => {
    loadDevices(currentPage)
    loadMetrics()
    setHasLoaded(true)
  }, [currentPage])

  // Handle settings changes
  useEffect(() => {
    const handleSettingsChange = (e: CustomEvent) => {
      if (e.detail.refreshInterval) {
        setRefreshInterval(parseInt(e.detail.refreshInterval) * 1000)
      }
    }

    window.addEventListener('settingsChanged', handleSettingsChange as EventListener)
    return () => window.removeEventListener('settingsChanged', handleSettingsChange as EventListener)
  }, [])

  // Filter devices by status
  const statusFiltered = filterDevices(devices, selectedFilter)
  
  // Apply search filter
  const filteredDevices = statusFiltered.filter((device) => {
    if (!searchQuery) return true
    const query = searchQuery.toLowerCase()
    return (
      device.alias.toLowerCase().includes(query) ||
      device.model?.toLowerCase().includes(query) ||
      device.manufacturer?.toLowerCase().includes(query) ||
      device.android_version?.toLowerCase().includes(query) ||
      device.build_id?.toLowerCase().includes(query)
    )
  })

  const handleRefresh = async () => {
    await loadDevices(currentPage)
    await loadMetrics()
  }

  const handleDeviceDeleted = async () => {
    await handleRefresh()
    setPreviousDeviceCount((prev) => Math.max(0, prev - 1))
  }

  const handleDeviceUpdated = async () => {
    await handleRefresh()
  }

  const handleToggleDark = () => {
    const newDark = !isDark
    setIsDark(newDark)
    localStorage.setItem('darkMode', newDark.toString())
  }

  const handleToggleSidebar = () => {
    const newState = !isSidebarOpen
    setIsSidebarOpen(newState)
    localStorage.setItem('sidebarOpen', newState.toString())
  }

  const handlePingDevice = async (deviceId: string) => {
    try {
      const response = await fetch(`/v1/devices/${deviceId}/ping`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      })

      const result = await response.json()

      if (!response.ok) {
        return {
          ok: false,
          error: result.error || 'Failed to ping device'
        }
      }

      setTimeout(async () => {
        await handleRefresh()
      }, 8000)

      return {
        ok: true,
        message: result.message || 'Ping sent successfully'
      }
    } catch (error) {
      return {
        ok: false,
        error: 'Network error: Failed to ping device'
      }
    }
  }

  const handleRingDevice = async (deviceId: string) => {
    try {
      const response = await fetch(`/v1/devices/${deviceId}/ring`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ duration: 30 }),
      })

      const result = await response.json()

      if (!response.ok) {
        return {
          ok: false,
          error: result.error || 'Failed to ring device'
        }
      }

      setTimeout(async () => {
        await handleRefresh()
      }, 8000)

      return {
        ok: true,
        message: result.message || 'Ring command sent successfully'
      }
    } catch (error) {
      return {
        ok: false,
        error: 'Network error: Failed to ring device'
      }
    }
  }

  const handleToggleDevice = (deviceId: string) => {
    setSelectedDeviceIds((prev) => {
      const newSet = new Set(prev)
      if (newSet.has(deviceId)) {
        newSet.delete(deviceId)
      } else {
        newSet.add(deviceId)
      }
      return newSet
    })
  }

  const handleToggleAll = () => {
    if (selectedDeviceIds.size === filteredDevices.length && filteredDevices.length > 0) {
      setSelectedDeviceIds(new Set())
    } else {
      setSelectedDeviceIds(new Set(filteredDevices.map((d) => d.id)))
    }
  }

  const handleBulkDelete = async () => {
    if (selectedDeviceIds.size === 0) return

    if (!confirm(`Are you sure you want to delete ${selectedDeviceIds.size} device(s)?`)) return

    setIsDeletingBulk(true)

    try {
      const response = await fetch('/v1/devices/bulk-delete', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          device_ids: Array.from(selectedDeviceIds),
        }),
      })

      const result = await response.json()

      if (!response.ok) {
        toast.error(result.error || 'Failed to delete devices')
        setIsDeletingBulk(false)
        return
      }

      toast.success(`${result.deleted_count} device(s) deleted successfully`)
      setSelectedDeviceIds(new Set())
      await handleRefresh()
      setPreviousDeviceCount((prev) => Math.max(0, prev - result.deleted_count))
    } catch (error) {
      toast.error('Failed to delete devices')
    } finally {
      setIsDeletingBulk(false)
    }
  }

  return (
    <div className="min-h-screen">
      <Sidebar isOpen={isSidebarOpen} onToggle={handleToggleSidebar} />
      
      <Header
        lastUpdated={lastUpdated}
        alertCount={metrics.low_battery}
        isDark={isDark}
        onToggleDark={handleToggleDark}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onRefresh={handleRefresh}
        onToggleSidebar={handleToggleSidebar}
      />

      <main className={`transition-all duration-300 px-6 pb-12 pt-[84px] md:px-8 ${isSidebarOpen ? 'lg:ml-64' : 'lg:ml-16'}`}>
        <KpiTiles 
          total={metrics.total} 
          online={metrics.online} 
          offline={metrics.offline} 
          alerts={metrics.low_battery}
          onAlertsClick={() => setIsAlertsDialogOpen(true)}
        />

        <FilterBar selected={selectedFilter} onSelect={setSelectedFilter} />

        <div className="mb-6 flex items-center justify-between gap-4">
          <div className="flex-1 max-w-md">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                placeholder="Search by alias, model, or Android version..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full rounded-lg border border-input bg-background pl-9 pr-4 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              />
            </div>
          </div>
          {selectedDeviceIds.size > 0 && (
            <Button
              variant="destructive"
              onClick={handleBulkDelete}
              disabled={isDeletingBulk}
              className="flex items-center gap-2"
            >
              {isDeletingBulk ? (
                <>
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                  Deleting...
                </>
              ) : (
                <>
                  <Trash2 className="h-4 w-4" />
                  Delete {selectedDeviceIds.size} device{selectedDeviceIds.size > 1 ? 's' : ''}
                </>
              )}
            </Button>
          )}
        </div>

        <DevicesTable 
          devices={filteredDevices} 
          onSelectDevice={setSelectedDevice} 
          onOpenSettings={() => setIsSettingsOpen(true)} 
          onPingDevice={handlePingDevice} 
          onRingDevice={handleRingDevice}
          selectedDeviceIds={selectedDeviceIds}
          onToggleDevice={handleToggleDevice}
          onToggleAll={handleToggleAll}
        />

        {pagination.total_pages > 1 && (
          <div className="mt-6 flex items-center justify-center gap-4">
            <Button
              variant="outline"
              onClick={() => setCurrentPage(currentPage - 1)}
              disabled={!pagination.has_prev}
            >
              Previous
            </Button>
            <span className="text-sm text-muted-foreground">
              Page {pagination.page} of {pagination.total_pages}
            </span>
            <Button
              variant="outline"
              onClick={() => setCurrentPage(currentPage + 1)}
              disabled={!pagination.has_next}
            >
              Next
            </Button>
          </div>
        )}
      </main>

      <DeviceDrawer 
        device={selectedDevice} 
        isOpen={!!selectedDevice} 
        onClose={() => setSelectedDevice(null)}
        onDeviceDeleted={handleDeviceDeleted}
        onDeviceUpdated={handleDeviceUpdated}
      />

      <SettingsDrawer isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} />

      <AlertsDialog
        open={isAlertsDialogOpen}
        onOpenChange={setIsAlertsDialogOpen}
        devices={devices}
        onSelectDevice={setSelectedDevice}
      />
    </div>
  )
}
