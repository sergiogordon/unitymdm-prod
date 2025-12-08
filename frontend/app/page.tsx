"use client"

import { useState, useEffect, useMemo } from "react"
import { useRouter, usePathname } from "next/navigation"
import { Header } from "@/components/header"
import { DashboardHeader } from "@/components/dashboard-header"
import { KpiTiles } from "@/components/kpi-tiles"
import { FilterBar } from "@/components/filter-bar"
import { DevicesTable } from "@/components/devices-table"
import { DeviceDrawer } from "@/components/device-drawer"
import { BackendStatusIndicator } from "@/components/backend-status-indicator"
import { type Device, type FilterType } from "@/lib/mock-data"
import { useDevices } from "@/hooks/use-devices"
import { isAuthenticated, fetchDeviceStats } from "@/lib/api-client"
import { useSettings } from "@/contexts/SettingsContext"
import { ArrowUpDown, Filter } from "lucide-react"
import {
  getLatestAgentVersion,
  getLatestUnityVersion,
  isVersionOutdated,
  type ApkBuild,
} from "@/lib/version-utils"
import {
  getCachedApkBuilds,
  setCachedApkBuilds,
} from "@/lib/apk-build-cache"
import { Checkbox } from "@/components/ui/checkbox"
import { Button } from "@/components/ui/button"

type AliasFilter = "all" | "D" | "S"
type SortOrder = "none" | "alias-asc" | "alias-desc"

function naturalSort(a: string, b: string): number {
  const regex = /(\d+)|(\D+)/g
  const aParts = a.match(regex) || []
  const bParts = b.match(regex) || []
  
  for (let i = 0; i < Math.max(aParts.length, bParts.length); i++) {
    const aPart = aParts[i] || ""
    const bPart = bParts[i] || ""
    
    const aNum = parseInt(aPart, 10)
    const bNum = parseInt(bPart, 10)
    
    if (!isNaN(aNum) && !isNaN(bNum)) {
      if (aNum !== bNum) return aNum - bNum
    } else {
      const cmp = aPart.localeCompare(bPart)
      if (cmp !== 0) return cmp
    }
  }
  return 0
}

export default function Page() {
  const router = useRouter()
  const pathname = usePathname()
  const { openSettings } = useSettings()
  const [lastUpdated, setLastUpdated] = useState(Date.now())
  const [selectedFilter, setSelectedFilter] = useState<FilterType>("all")
  const [aliasFilter, setAliasFilter] = useState<AliasFilter>("all")
  const [sortOrder, setSortOrder] = useState<SortOrder>("none")
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null)
  const [authChecked, setAuthChecked] = useState(false)
  
  // Version filtering state
  const [allApkBuilds, setAllApkBuilds] = useState<ApkBuild[]>([])
  const [filterOutdatedAgent, setFilterOutdatedAgent] = useState(false)
  const [filterOutdatedUnity, setFilterOutdatedUnity] = useState(false)
  
  // Separate stats state for accurate KPI counters
  const [stats, setStats] = useState({ total: 0, online: 0, offline: 0, low_battery: 0 })

  // Track setup check status to sync with SetupCheck component
  const [setupReady, setSetupReady] = useState(() => {
    if (typeof window !== 'undefined') {
      return sessionStorage.getItem('setup_checked') === 'ready'
    }
    return false
  })

  // Listen for sessionStorage changes to sync with SetupCheck completion
  useEffect(() => {
    const checkSetupStatus = () => {
      if (typeof window !== 'undefined') {
        const setupChecked = sessionStorage.getItem('setup_checked')
        setSetupReady(setupChecked === 'ready')
      }
    }

    // Check immediately
    checkSetupStatus()

    // Listen for storage events (when SetupCheck updates sessionStorage)
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === 'setup_checked') {
        checkSetupStatus()
      }
    }

    window.addEventListener('storage', handleStorageChange)

    // Also poll periodically to catch same-tab updates (storage event only fires for other tabs)
    const interval = setInterval(checkSetupStatus, 100)

    return () => {
      window.removeEventListener('storage', handleStorageChange)
      clearInterval(interval)
    }
  }, [])

  // Check authentication, but only after SetupCheck confirms setup is complete
  // SetupCheck component wraps this page and will redirect to /setup if setup is incomplete
  useEffect(() => {
    // Only proceed with auth check if:
    // 1. We're still on root path (SetupCheck hasn't redirected us)
    // 2. Setup is confirmed complete
    if (pathname !== '/') {
      // SetupCheck redirected us, don't proceed with auth check
      return
    }

    if (!setupReady) {
      // Setup not confirmed complete - SetupCheck should handle redirect
      // Don't proceed with auth check yet
      return
    }

    // Setup is confirmed complete, proceed with auth check
    if (!isAuthenticated()) {
      router.push('/login')
    } else {
      setAuthChecked(true)
    }
  }, [router, pathname, setupReady])
  
  // Fetch stats for KPIs (all devices, not just visible ones)
  useEffect(() => {
    if (authChecked) {
      fetchDeviceStats()
        .then(setStats)
        .catch(err => console.error('Failed to fetch stats:', err))
    }
  }, [authChecked, lastUpdated])

  // Fetch APK builds for version comparison (with caching)
  useEffect(() => {
    if (authChecked) {
      const fetchApkBuilds = async () => {
        try {
          // Check cache first
          const cached = getCachedApkBuilds('release', 50)
          if (cached) {
            setAllApkBuilds(cached)
            // Fetch in background to refresh cache
            fetch('/admin/apk/builds?build_type=release&limit=50')
              .then(res => res.ok ? res.json() : null)
              .then(data => {
                if (data?.builds) {
                  setCachedApkBuilds('release', 50, data.builds)
                  setAllApkBuilds(data.builds)
                }
              })
              .catch(() => {}) // Silent fail for background refresh
          } else {
            // Fetch and cache
            const response = await fetch('/admin/apk/builds?build_type=release&limit=50')
            if (response.ok) {
              const data = await response.json()
              const builds = data.builds || []
              setAllApkBuilds(builds)
              setCachedApkBuilds('release', 50, builds)
            }
          }
        } catch (err) {
          console.error('Failed to fetch APK builds:', err)
        }
      }
      fetchApkBuilds()
    }
  }, [authChecked])
  
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

  // Calculate latest versions from APK builds
  const latestAgentVersion = useMemo(() => {
    return getLatestAgentVersion(allApkBuilds)
  }, [allApkBuilds])

  const latestUnityVersion = useMemo(() => {
    return getLatestUnityVersion(allApkBuilds)
  }, [allApkBuilds])

  // Filter and sort devices
  const filteredAndSortedDevices = useMemo(() => {
    let result = devices.filter((device) => {
      if (selectedFilter === "offline" && device.status !== "offline") return false
      if (selectedFilter === "unity-down" && device.unity.status !== "down") return false
      if (selectedFilter === "low-battery" && device.battery.percentage >= 20) return false
      if (selectedFilter === "wrong-version" && device.unity.version === "1.2.3") return false
      
      if (aliasFilter !== "all") {
        if (!device.alias.toUpperCase().startsWith(aliasFilter)) return false
      }
      
      // Version filtering
      if (filterOutdatedAgent || filterOutdatedUnity) {
        const agentOutdated = filterOutdatedAgent
          ? isVersionOutdated(device.agent?.version, latestAgentVersion)
          : false
        const unityOutdated = filterOutdatedUnity
          ? isVersionOutdated(device.unity?.version, latestUnityVersion)
          : false
        
        // Show device if it's outdated in at least one category when filters are active
        if (!agentOutdated && !unityOutdated) {
          return false
        }
      }
      
      return true
    })
    
    if (sortOrder === "alias-asc") {
      result = [...result].sort((a, b) => naturalSort(a.alias, b.alias))
    } else if (sortOrder === "alias-desc") {
      result = [...result].sort((a, b) => naturalSort(b.alias, a.alias))
    } else if (sortOrder === "none") {
      // Default sort: S devices first, then D devices, then A-Z
      result = [...result].sort((a, b) => {
        const aAlias = a.alias.toUpperCase()
        const bAlias = b.alias.toUpperCase()
        const aStartsWithS = aAlias.startsWith('S')
        const bStartsWithS = bAlias.startsWith('S')
        const aStartsWithD = aAlias.startsWith('D')
        const bStartsWithD = bAlias.startsWith('D')
        
        if (aStartsWithS && !bStartsWithS) return -1
        if (!aStartsWithS && bStartsWithS) return 1
        
        if (aStartsWithD && !bStartsWithD && !bStartsWithS) return -1
        if (!aStartsWithD && bStartsWithD && !aStartsWithS) return 1
        
        const aMatch = aAlias.match(/^([A-Z]+)(\d+)?/)
        const bMatch = bAlias.match(/^([A-Z]+)(\d+)?/)
        
        if (aMatch && bMatch) {
          const aPrefix = aMatch[1]
          const bPrefix = bMatch[1]
          
          if (aPrefix !== bPrefix) {
            return aPrefix.localeCompare(bPrefix)
          }
          
          const aNum = aMatch[2] ? parseInt(aMatch[2], 10) : 0
          const bNum = bMatch[2] ? parseInt(bMatch[2], 10) : 0
          const numComparison = aNum - bNum
          if (numComparison !== 0) {
            return numComparison
          }
          // If numeric values are equal, fall back to full alias comparison
          return aAlias.localeCompare(bAlias)
        }
        
        return aAlias.localeCompare(bAlias)
      })
    }
    
    return result
  }, [devices, selectedFilter, aliasFilter, sortOrder, filterOutdatedAgent, filterOutdatedUnity, latestAgentVersion, latestUnityVersion])

  const filteredDevices = filteredAndSortedDevices

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
      <Header />
      
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
          onOpenSettings={openSettings}
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

        {/* Version Filters */}
        {(filterOutdatedAgent || filterOutdatedUnity || latestAgentVersion || latestUnityVersion) && (
          <div className="mb-4 rounded-lg border border-border bg-muted/50 p-4">
            <div className="mb-3 text-sm font-medium text-card-foreground">Version Filters</div>
            <div className="flex flex-wrap items-center gap-4">
              <div className="flex items-center gap-2">
                <Checkbox
                  id="filter-outdated-agent-dashboard"
                  checked={filterOutdatedAgent}
                  onCheckedChange={(checked) => setFilterOutdatedAgent(checked === true)}
                  disabled={!latestAgentVersion}
                />
                <label
                  htmlFor="filter-outdated-agent-dashboard"
                  className="text-sm cursor-pointer"
                >
                  Show only devices with outdated Agent version
                </label>
                {latestAgentVersion && (
                  <span className="text-xs text-muted-foreground ml-2">
                    (Latest: {latestAgentVersion})
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <Checkbox
                  id="filter-outdated-unity-dashboard"
                  checked={filterOutdatedUnity}
                  onCheckedChange={(checked) => setFilterOutdatedUnity(checked === true)}
                  disabled={!latestUnityVersion}
                />
                <label
                  htmlFor="filter-outdated-unity-dashboard"
                  className="text-sm cursor-pointer"
                >
                  Show only devices with outdated Unity version
                </label>
                {latestUnityVersion && (
                  <span className="text-xs text-muted-foreground ml-2">
                    (Latest: {latestUnityVersion})
                  </span>
                )}
              </div>
              {(filterOutdatedAgent || filterOutdatedUnity) && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setFilterOutdatedAgent(false)
                    setFilterOutdatedUnity(false)
                  }}
                  className="h-7 text-xs"
                >
                  Clear version filters
                </Button>
              )}
            </div>
          </div>
        )}

        <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <Filter className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">Alias:</span>
            </div>
            <div className="inline-flex rounded-lg bg-muted p-1">
              {(["all", "S", "D"] as AliasFilter[]).map((filter) => (
                <button
                  key={filter}
                  onClick={() => setAliasFilter(filter)}
                  className={`rounded-md px-3 py-1.5 text-sm font-medium transition-all ${
                    aliasFilter === filter
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {filter === "all" ? "All" : filter}
                </button>
              ))}
            </div>
            {aliasFilter !== "all" && (
              <span className="text-sm text-muted-foreground">
                ({filteredDevices.length} devices)
              </span>
            )}
          </div>
          
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <ArrowUpDown className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">Sort:</span>
            </div>
            <div className="inline-flex rounded-lg bg-muted p-1">
              <button
                onClick={() => setSortOrder("none")}
                className={`rounded-md px-3 py-1.5 text-sm font-medium transition-all ${
                  sortOrder === "none"
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                Default
              </button>
              <button
                onClick={() => setSortOrder("alias-asc")}
                className={`rounded-md px-3 py-1.5 text-sm font-medium transition-all ${
                  sortOrder === "alias-asc"
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                A-Z
              </button>
              <button
                onClick={() => setSortOrder("alias-desc")}
                className={`rounded-md px-3 py-1.5 text-sm font-medium transition-all ${
                  sortOrder === "alias-desc"
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                Z-A
              </button>
            </div>
          </div>
        </div>

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

      <DeviceDrawer 
        device={selectedDevice} 
        isOpen={!!selectedDevice} 
        onClose={() => setSelectedDevice(null)}
        onDeviceUpdated={handleRefresh}
      />

      <BackendStatusIndicator />
    </div>
  )
}
