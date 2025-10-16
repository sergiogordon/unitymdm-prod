"use client"

import { useState, useEffect } from "react"
import { Header } from "@/components/header"
import { KpiTiles } from "@/components/kpi-tiles"
import { FilterBar } from "@/components/filter-bar"
import { DevicesTable } from "@/components/devices-table"
import { DeviceDrawer } from "@/components/device-drawer"
import { SettingsDrawer } from "@/components/settings-drawer"
import { mockDevices, type Device, type FilterType } from "@/lib/mock-data"

export default function Page() {
  const [isDark, setIsDark] = useState(false)
  const [lastUpdated, setLastUpdated] = useState(Date.now())
  const [selectedFilter, setSelectedFilter] = useState<FilterType>("all")
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null)
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  const [devices, setDevices] = useState(mockDevices)

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
    // In a real app, this would fetch new data
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

      <main className="mx-auto max-w-[1280px] px-6 pb-12 pt-[84px] md:px-8">
        <KpiTiles
          total={totalDevices}
          online={onlineDevices}
          offline={offlineDevices}
          alerts={activeAlerts}
          devices={devices}
        />

        <FilterBar selected={selectedFilter} onSelect={setSelectedFilter} />

        <DevicesTable devices={filteredDevices} onSelectDevice={setSelectedDevice} />
      </main>

      <DeviceDrawer device={selectedDevice} isOpen={!!selectedDevice} onClose={() => setSelectedDevice(null)} />

      <SettingsDrawer isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} />
    </div>
  )
}
