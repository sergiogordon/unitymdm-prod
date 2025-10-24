"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { Header } from "@/components/header"
import { DashboardHeader } from "@/components/dashboard-header"
import { KpiTiles } from "@/components/kpi-tiles"
import { FilterBar } from "@/components/filter-bar"
import { DevicesTable } from "@/components/devices-table"
import { DeviceDrawer } from "@/components/device-drawer"
import { SettingsDrawer } from "@/components/settings-drawer"
import { type Device, type FilterType } from "@/lib/mock-data"
import { useDevices } from "@/hooks/use-devices"
import { isAuthenticated, fetchDeviceStats } from "@/lib/api-client"
import { useTheme } from "@/contexts/ThemeContext"

export default function Page() {
  const router = useRouter()
  const { isDark, toggleTheme } = useTheme()
  const [lastUpdated, setLastUpdated] = useState(Date.now())
  const [selectedFilter, setSelectedFilter] = useState<FilterType>("all")
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null)
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  const [authChecked, setAuthChecked] = useState(false)
  
  // Separate stats state for accurate KPI counters
  const [stats, setStats] = useState({ total: 0, online: 0, offline: 0, low_battery: 0 })

  // Check authentication first
  useEffect(() => {
    if (!isAuthenticated()) {
      router.push('/login')
    } else {
      setAuthChecked(true)
    }
  }, [router])
  
  // Fetch stats for KPIs (all devices, not just visible ones)
  useEffect(() => {
    if (authChecked) {
      fetchDeviceStats()
        .then(setStats)
        .catch(err => console.error('Failed to fetch stats:', err))
    }
  }, [authChecked, lastUpdated])
  
  // Only fetch devices after auth is confirmed
  const shouldFetch = authChecked
  const { 
    devices, 
    loading, 
    error, 
    refresh, 
    wsConnected,
    pagination,
    currentPage,
    pageSize,
    nextPage,
    prevPage,
    changePageSize
  } = useDevices(shouldFetch)

  // Filter devices (only filters the current page)
  const filteredDevices = devices.filter((device) => {
    if (selectedFilter === "all") return true
    if (selectedFilter === "offline") return device.status === "offline"
    if (selectedFilter === "unity-down") return device.unity.status === "down"
    if (selectedFilter === "low-battery") return device.battery.percentage < 20
    if (selectedFilter === "wrong-version") return device.unity.version !== "1.2.3"
    return true
  })

  // Active alerts from full stats
  const activeAlerts = stats.offline + stats.low_battery

  const handleRefresh = () => {
    setLastUpdated(Date.now())
    refresh() // Fetch fresh data from backend
  }

  // Show loading state
  if (loading && devices.length === 0) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gray-900 dark:border-gray-100 mx-auto mb-4"></div>
          <p className="text-muted-foreground">Loading devices...</p>
        </div>
      </div>
    )
  }

  // Show error state
  if (error && devices.length === 0) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-600 dark:text-red-400 mb-4">Error: {error}</p>
          <button 
            onClick={handleRefresh}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen">
      <Header
        isDark={isDark}
        onToggleDark={toggleTheme}
      />
      
      {/* Show WebSocket status indicator */}
      {wsConnected && (
        <div className="fixed top-20 right-6 z-50">
          <div className="flex items-center gap-2 px-3 py-1.5 bg-green-500/10 border border-green-500/20 rounded-full">
            <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
            <span className="text-xs text-green-600 dark:text-green-400">Live</span>
          </div>
        </div>
      )}

      <main className="mx-auto max-w-[1280px] px-6 pb-12 pt-[84px] md:px-8">
        <DashboardHeader
          lastUpdated={lastUpdated}
          alertCount={activeAlerts}
          onOpenSettings={() => setIsSettingsOpen(true)}
          onRefresh={handleRefresh}
        />

        <KpiTiles
          total={stats.total}
          online={stats.online}
          offline={stats.offline}
          alerts={activeAlerts}
          devices={devices}
        />

        <FilterBar selected={selectedFilter} onSelect={setSelectedFilter} />

        <DevicesTable 
          devices={filteredDevices} 
          onSelectDevice={setSelectedDevice}
          onDevicesDeleted={refresh}
          pagination={pagination}
          currentPage={currentPage}
          pageSize={pageSize}
          onNextPage={nextPage}
          onPrevPage={prevPage}
          onChangePageSize={changePageSize}
        />
      </main>

      <DeviceDrawer device={selectedDevice} isOpen={!!selectedDevice} onClose={() => setSelectedDevice(null)} />

      <SettingsDrawer isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} />
    </div>
  )
}
