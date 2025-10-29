"use client"

import { useState, useEffect, useCallback } from "react"
import { Header } from "@/components/header"
import { Sidebar } from "@/components/sidebar"
import { KpiTiles } from "@/components/kpi-tiles"
import { FilterBar } from "@/components/filter-bar"
import { DevicesTable } from "@/components/devices-table"
import { DeviceDrawer } from "@/components/device-drawer"
import { SettingsDrawer } from "@/components/settings-drawer"
import { AlertsDialog } from "@/components/alerts-dialog"
import { Button } from "@/components/ui/button"
import { DemoApiService } from "@/lib/demoApiService"
import { toast } from "sonner"
import type { Device, FilterType } from "@/lib/mock-data"

interface MetricsResponse {
  total: number
  online: number
  offline: number
  low_battery: number
}
import { useTheme } from "@/contexts/ThemeContext"

export const dynamic = 'force-dynamic'

export default function DemoDashboard() {
  const { isDark, toggleTheme } = useTheme()
  const [isSidebarOpen, setIsSidebarOpen] = useState(true)
  const [devices, setDevices] = useState<Device[]>([])
  const [metrics, setMetrics] = useState<MetricsResponse>({
    total: 0,
    online: 0,
    offline: 0,
    low_battery: 0
  })
  const [filterType, setFilterType] = useState<FilterType>("all")
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null)
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  const [isAlertsOpen, setIsAlertsOpen] = useState(false)
  const [lastUpdated, setLastUpdated] = useState(Date.now())
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [searchQuery, setSearchQuery] = useState("")

  const loadData = useCallback(async () => {
    try {
      const metricsResponse = await DemoApiService.fetch('/v1/metrics')
      const metricsData = await metricsResponse.json()
      setMetrics(metricsData)

      const devicesResponse = await DemoApiService.fetch(`/v1/devices?page=${page}&limit=25`)
      const devicesData = await devicesResponse.json()
      setDevices(devicesData.devices)
      setTotalPages(devicesData.pagination.total_pages)
      setLastUpdated(Date.now())
    } catch (error) {
      console.error('Failed to load demo data:', error)
    }
  }, [page])

  useEffect(() => {
    loadData()
  }, [loadData])

  const handleToggleSidebar = () => {
    setIsSidebarOpen(!isSidebarOpen)
  }

  const handleFilterChange = (filter: FilterType) => {
    setFilterType(filter)
  }

  const handleDeviceClick = (device: Device) => {
    setSelectedDevice(device)
  }

  const handleRefresh = () => {
    loadData()
    toast.success('Demo data refreshed')
  }

  const handleDeleteDevice = async (deviceId: string) => {
    toast.info('Delete disabled in demo mode')
  }

  const filteredDevices = devices.filter(device => {
    const matchesFilter = filterType === "all" || device.status === filterType
    const matchesSearch = searchQuery === "" || 
      device.alias.toLowerCase().includes(searchQuery.toLowerCase()) ||
      device.id.toLowerCase().includes(searchQuery.toLowerCase())
    return matchesFilter && matchesSearch
  })

  return (
    <div className="min-h-screen">
      <Sidebar isOpen={isSidebarOpen} onToggle={handleToggleSidebar} />
      
      <Header
        lastUpdated={lastUpdated}
        alertCount={metrics.low_battery}
        isDark={isDark}
        onToggleDark={toggleTheme}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onRefresh={handleRefresh}
        onToggleSidebar={handleToggleSidebar}
      />

      <main className={`transition-all duration-300 px-6 pb-12 pt-20 md:px-8 ${isSidebarOpen ? 'lg:ml-64' : 'lg:ml-16'}`}>
        <KpiTiles 
          total={metrics.total} 
          online={metrics.online} 
          offline={metrics.offline} 
          low_battery={metrics.low_battery} 
        />

        <div className="space-y-6">
          <FilterBar 
            filter={filterType}
            onFilterChange={handleFilterChange}
            search={searchQuery}
            onSearchChange={setSearchQuery}
          />

          <DevicesTable 
            devices={filteredDevices}
            onClick={handleDeviceClick}
            onDelete={handleDeleteDevice}
            selectedDeviceIds={new Set()}
            onDeviceSelect={() => {}}
            onSelectAll={() => {}}
          />

          {totalPages > 1 && (
            <div className="flex justify-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
              >
                Previous
              </Button>
              <span className="px-4 py-2 text-sm">
                Page {page} of {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
              >
                Next
              </Button>
            </div>
          )}
        </div>
      </main>

      <DeviceDrawer 
        device={selectedDevice}
        isOpen={!!selectedDevice}
        onClose={() => setSelectedDevice(null)}
      />

      <SettingsDrawer 
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
      />

      <AlertsDialog 
        open={isAlertsOpen}
        onOpenChange={(open) => setIsAlertsOpen(open)}
        devices={devices}
        onSelectDevice={handleDeviceClick}
      />
    </div>
  )
}
