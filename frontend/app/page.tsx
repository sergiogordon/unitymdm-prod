"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { Header } from "@/components/header"
import { KpiTiles } from "@/components/kpi-tiles"
import { FilterBar } from "@/components/filter-bar"
import { DevicesTable } from "@/components/devices-table"
import { DeviceDrawer } from "@/components/device-drawer"
import { SettingsDrawer } from "@/components/settings-drawer"
import { type Device, type FilterType } from "@/lib/mock-data"
import { useDevices } from "@/hooks/use-devices"
import { isAuthenticated } from "@/lib/api-client"

export default function Page() {
  const router = useRouter()
  const [isDark, setIsDark] = useState(false)
  const [lastUpdated, setLastUpdated] = useState(Date.now())
  const [selectedFilter, setSelectedFilter] = useState<FilterType>("all")
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null)
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  const [authChecked, setAuthChecked] = useState(false)

  // Check authentication first
  useEffect(() => {
    if (!isAuthenticated()) {
      router.push('/login')
    } else {
      setAuthChecked(true)
    }
  }, [router])
  
  // Only fetch devices after auth is confirmed
  const shouldFetch = authChecked
  const { devices, loading, error, refresh, wsConnected } = useDevices(shouldFetch)

  // Toggle dark mode
  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add("dark")
    } else {
      document.documentElement.classList.remove("dark")
    }
  }, [isDark])

  // Filter devices
  const filteredDevices = devices.filter((device) => {
    if (selectedFilter === "all") return true
    if (selectedFilter === "offline") return device.status === "offline"
    if (selectedFilter === "unity-down") return device.unity.status === "down"
    if (selectedFilter === "low-battery") return device.battery.percentage < 20
    if (selectedFilter === "wrong-version") return device.unity.version !== "1.2.3"
    return true
  })

  // Calculate KPIs
  const totalDevices = devices.length
  const onlineDevices = devices.filter((d) => d.status === "online").length
  const offlineDevices = devices.filter((d) => d.status === "offline").length
  const activeAlerts = devices.filter(
    (d) => d.status === "offline" || d.unity.status === "down" || d.battery.percentage < 20,
  ).length

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
        lastUpdated={lastUpdated}
        alertCount={activeAlerts}
        isDark={isDark}
        onToggleDark={() => setIsDark(!isDark)}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onRefresh={handleRefresh}
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
        <KpiTiles
          total={totalDevices}
          online={onlineDevices}
          offline={offlineDevices}
          alerts={activeAlerts}
          devices={devices}
        />

        <FilterBar selected={selectedFilter} onSelect={setSelectedFilter} />

        <DevicesTable 
          devices={filteredDevices} 
          onSelectDevice={setSelectedDevice}
          onDevicesDeleted={refresh}
        />
      </main>

      <DeviceDrawer device={selectedDevice} isOpen={!!selectedDevice} onClose={() => setSelectedDevice(null)} />

      <SettingsDrawer isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} />
    </div>
  )
}
