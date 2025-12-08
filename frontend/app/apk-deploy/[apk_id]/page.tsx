"use client"

import { useState, useEffect, useMemo } from "react"
import { useParams, useRouter } from "next/navigation"
import { Header } from "@/components/header"
import { PageHeader } from "@/components/page-header"
import { ArrowLeft, Send, CheckCircle2, XCircle, Loader2, Search, Clock, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Label } from "@/components/ui/label"
import {
  getLatestAgentVersion,
  getLatestUnityVersion,
  isVersionOutdated,
  type ApkBuild as ApkBuildType,
} from "@/lib/version-utils"
import {
  getCachedApkBuilds,
  setCachedApkBuilds,
  clearApkBuildCache,
} from "@/lib/apk-build-cache"

interface Device {
  id: string
  alias: string
  fcm_token: string | null
  last_seen: string
  status: "online" | "offline"
  last_status?: {
    agent?: { version?: string }
    unity?: { version?: string; status?: string }
  }
}

interface ApkBuild {
  build_id: number
  filename: string
  version_name: string
  version_code: number
  file_size_bytes: number
}

interface DeploymentResult {
  success: number
  failed: number
  total: number
  details: Array<{
    device_id: string
    alias: string
    success: boolean
    reason?: string
  }>
}

interface RecentDeployment {
  id: number
  apk_id: number
  device_id: string
  status: string
  created_at: string
  apk?: {
    filename: string
    version_name: string
    package_name: string
  }
  device?: {
    alias: string
  }
}

export default function ApkDeployPage() {
  const params = useParams()
  const router = useRouter()
  const apkId = params.apk_id as string
  
  const [apk, setApk] = useState<ApkBuild | null>(null)
  const [devices, setDevices] = useState<Device[]>([])
  const [selectedDevices, setSelectedDevices] = useState<Set<string>>(new Set())
  const [isLoading, setIsLoading] = useState(true)
  const [isDeploying, setIsDeploying] = useState(false)
  const [deploymentResult, setDeploymentResult] = useState<DeploymentResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [rolloutStrategy, setRolloutStrategy] = useState<"all" | "25" | "50" | "custom">("all")
  const [customPercentage, setCustomPercentage] = useState<number>(10)
  const [showConfirmModal, setShowConfirmModal] = useState(false)
  const [aliasFilter, setAliasFilter] = useState("")
  const [recentDeployments, setRecentDeployments] = useState<RecentDeployment[]>([])
  const [loadingRecentDeployments, setLoadingRecentDeployments] = useState(false)
  
  // Version filtering state
  const [allApkBuilds, setAllApkBuilds] = useState<ApkBuildType[]>([])
  const [filterOutdatedAgent, setFilterOutdatedAgent] = useState(false)
  const [filterOutdatedUnity, setFilterOutdatedUnity] = useState(false)
  
  // Batching state
  const [isBatching, setIsBatching] = useState(false)
  const [currentBatch, setCurrentBatch] = useState(0)
  const [totalBatches, setTotalBatches] = useState(0)
  const [batchProgress, setBatchProgress] = useState<Map<string, { status: string; progress?: number }>>(new Map())
  const [batchResults, setBatchResults] = useState<DeploymentResult[]>([])
  const [cancelled, setCancelled] = useState(false)

  // Detect APK type from filename
  const apkType = useMemo(() => {
    if (!apk?.filename) return null
    const filename = apk.filename.toLowerCase()
    if (filename.startsWith('com.')) return 'agent'
    if (filename.startsWith('unity')) return 'unity'
    return null
  }, [apk?.filename])

  // Calculate latest versions from APK builds
  const latestAgentVersion = useMemo(() => {
    return getLatestAgentVersion(allApkBuilds)
  }, [allApkBuilds])

  const latestUnityVersion = useMemo(() => {
    return getLatestUnityVersion(allApkBuilds)
  }, [allApkBuilds])

  const filteredDevices = useMemo(() => {
    let result = [...devices]
    
    if (aliasFilter.trim()) {
      const filterLower = aliasFilter.toLowerCase()
      result = result.filter(device => 
        device.alias.toLowerCase().startsWith(filterLower)
      )
    }
    
    // Version filtering
    if (filterOutdatedAgent || filterOutdatedUnity) {
      result = result.filter(device => {
        const agentOutdated = filterOutdatedAgent 
          ? isVersionOutdated(device.last_status?.agent?.version, latestAgentVersion)
          : false
        const unityOutdated = filterOutdatedUnity
          ? isVersionOutdated(device.last_status?.unity?.version, latestUnityVersion)
          : false
        
        // Show device if it's outdated in at least one category when filters are active
        return agentOutdated || unityOutdated
      })
    }
    
    result.sort((a, b) => {
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
        return aNum - bNum
      }
      
      return aAlias.localeCompare(bAlias)
    })
    
    return result
  }, [devices, aliasFilter, filterOutdatedAgent, filterOutdatedUnity, latestAgentVersion, latestUnityVersion])

  useEffect(() => {
    fetchData()
    fetchRecentDeployments()
  }, [apkId])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (isDeploying) {
        setCancelled(true)
      }
    }
  }, [isDeploying])

  const fetchData = async () => {
    setIsLoading(true)
    setError(null)
    
    try {
      // Get auth token from localStorage
      const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null
      
      if (!token) {
        throw new Error('Authentication required')
      }

      // Check cache first for APK builds
      const cachedBuilds = getCachedApkBuilds(undefined, 100)
      let builds: ApkBuildType[] = []
      
      if (cachedBuilds) {
        builds = cachedBuilds
        setAllApkBuilds(builds)
        // Fetch in background to refresh cache
        fetch(`/admin/apk/builds?limit=100&order=desc`)
          .then(res => res.ok ? res.json() : null)
          .then(data => {
            if (data?.builds) {
              setCachedApkBuilds(undefined, 100, data.builds)
              setAllApkBuilds(data.builds)
            }
          })
          .catch(() => {}) // Silent fail for background refresh
      }

      // Fetch APK details and devices in parallel
      const [apkRes, devicesRes] = await Promise.all([
        cachedBuilds ? Promise.resolve({ ok: true, json: async () => ({ builds }) }) : fetch(`/admin/apk/builds?limit=100&order=desc`),
        fetch('/api/proxy/v1/devices?page=1&limit=200', {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        })
      ])

      if (!apkRes.ok || !devicesRes.ok) {
        throw new Error('Failed to fetch data')
      }

      const apkData = await apkRes.json()
      const devicesData = await devicesRes.json()

      // Store all APK builds for version comparison
      builds = apkData.builds || []
      setAllApkBuilds(builds)
      
      // Cache the builds
      if (!cachedBuilds) {
        setCachedApkBuilds(undefined, 100, builds)
      }

      // Find the specific APK by build_id
      const targetApk = builds.find((b: ApkBuild) => b.build_id === parseInt(apkId))
      
      if (targetApk) {
        setApk(targetApk)
      } else {
        throw new Error('APK not found')
      }

      setDevices(devicesData.devices || [])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data')
      console.error('Error fetching data:', err)
    } finally {
      setIsLoading(false)
    }
  }

  const fetchRecentDeployments = async () => {
    setLoadingRecentDeployments(true)
    try {
      const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null
      if (!token) return

      const response = await fetch('/v1/apk/installations?limit=3', {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      })

      if (response.ok) {
        const data = await response.json()
        setRecentDeployments(Array.isArray(data) ? data.slice(0, 3) : [])
      }
    } catch (error) {
      console.error('Failed to fetch recent deployments:', error)
    } finally {
      setLoadingRecentDeployments(false)
    }
  }

  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      const deviceIdsToSelect = filteredDevices.map(d => d.id)
      setSelectedDevices(prev => {
        const newSet = new Set(prev)
        deviceIdsToSelect.forEach(id => newSet.add(id))
        return newSet
      })
    } else {
      const filteredIds = new Set(filteredDevices.map(d => d.id))
      setSelectedDevices(prev => {
        const newSet = new Set(prev)
        filteredIds.forEach(id => newSet.delete(id))
        return newSet
      })
    }
  }

  const handleToggleDevice = (deviceId: string) => {
    const newSelection = new Set(selectedDevices)
    if (newSelection.has(deviceId)) {
      newSelection.delete(deviceId)
    } else {
      newSelection.add(deviceId)
    }
    setSelectedDevices(newSelection)
  }

  const getDeploymentDevices = (): string[] => {
    const allSelected = Array.from(selectedDevices)
    
    if (rolloutStrategy === "all") {
      return allSelected
    }
    
    let percentage: number
    if (rolloutStrategy === "25") {
      percentage = 25
    } else if (rolloutStrategy === "50") {
      percentage = 50
    } else {
      percentage = customPercentage
    }
    
    const count = Math.max(1, Math.ceil((allSelected.length * percentage) / 100))
    return allSelected.slice(0, count)
  }

  const handleDeployClick = () => {
    if (selectedDevices.size === 0) {
      alert('Please select at least one device')
      return
    }
    setShowConfirmModal(true)
  }

  const pollInstallationStatus = async (
    deviceIds: string[],
    apkId: number,
    maxWaitTime: number = 5 * 60 * 1000 // 5 minutes
  ): Promise<Map<string, { status: string; progress?: number }>> => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null
    if (!token) {
      throw new Error('Authentication required')
    }

    const startTime = Date.now()
    const pollInterval = 2000 // 2 seconds
    const terminalStatuses = ['completed', 'failed', 'timeout']
    const statusMap = new Map<string, { status: string; progress?: number }>()

    // Initialize all devices as pending
    deviceIds.forEach(id => {
      statusMap.set(id, { status: 'pending' })
    })

    let pollCount = 0
    const maxPollAttempts = Math.floor(maxWaitTime / pollInterval)

    while (pollCount < maxPollAttempts) {
      if (cancelled) {
        // Mark all pending as cancelled
        deviceIds.forEach(deviceId => {
          if (!terminalStatuses.includes(statusMap.get(deviceId)?.status || '')) {
            statusMap.set(deviceId, { status: 'timeout' })
          }
        })
        setBatchProgress(new Map(statusMap))
        return statusMap
      }

      try {
        const response = await fetch(`/v1/apk/installations?apk_id=${apkId}`, {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        })

        if (!response.ok) {
          // Retry on error, but don't fail immediately
          await new Promise(resolve => setTimeout(resolve, pollInterval))
          continue
        }

        const installations = await response.json()
        const installationsArray = Array.isArray(installations) ? installations : []

        // Update status for each device
        let allTerminal = true
        deviceIds.forEach(deviceId => {
          const installation = installationsArray.find((inst: any) => inst.device_id === deviceId)
          if (installation) {
            const status = installation.status || 'pending'
            statusMap.set(deviceId, {
              status,
              progress: installation.download_progress || 0
            })
            
            if (!terminalStatuses.includes(status)) {
              allTerminal = false
            }
          } else {
            // Installation not found yet, still pending
            allTerminal = false
          }
        })

        // Update batch progress state
        setBatchProgress(new Map(statusMap))

        if (allTerminal) {
          return statusMap
        }
      } catch (error) {
        console.error('Error polling installation status:', error)
        // Continue polling on error, but increment count
        pollCount++
        if (pollCount < maxPollAttempts) {
          await new Promise(resolve => setTimeout(resolve, pollInterval))
        }
        continue
      }

      pollCount++
      if (pollCount < maxPollAttempts) {
        await new Promise(resolve => setTimeout(resolve, pollInterval))
      }
    }

    // Timeout reached - mark remaining pending devices as timeout
    deviceIds.forEach(deviceId => {
      if (!statusMap.has(deviceId) || !terminalStatuses.includes(statusMap.get(deviceId)!.status)) {
        statusMap.set(deviceId, { status: 'timeout' })
      }
    })

    setBatchProgress(new Map(statusMap))
    return statusMap
  }

  // Deploy a batch (API call only, no polling)
  const deployBatchApi = async (
    batchDevices: string[],
    apkId: number,
    rolloutPercent: number,
    retries: number = 3
  ): Promise<{ installationIds: string[], failedDevices: any[] }> => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null
    
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    }
    
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }

    let lastError: Error | null = null

    for (let attempt = 0; attempt < retries; attempt++) {
      if (cancelled) {
        throw new Error('Deployment cancelled')
      }

      try {
        const response = await fetch('/v1/apk/deploy', {
          method: 'POST',
          headers,
          body: JSON.stringify({
            apk_id: apkId,
            device_ids: batchDevices,
            rollout_percent: rolloutPercent
          })
        })

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}))
          throw new Error(errorData.detail || `Deployment failed with status ${response.status}`)
        }

        const result = await response.json()
        
        // Extract installation IDs for polling
        const installationIds = (result.installations || []).map((inst: any) => inst.device?.id || inst.device_id).filter(Boolean)
        
        return {
          installationIds,
          failedDevices: result.failed_devices || []
        }
      } catch (error) {
        lastError = error instanceof Error ? error : new Error(String(error))
        
        // Exponential backoff for retries
        if (attempt < retries - 1) {
          const backoffDelay = Math.min(1000 * Math.pow(2, attempt), 10000)
          await new Promise(resolve => setTimeout(resolve, backoffDelay))
        }
      }
    }

    // All retries failed
    throw lastError || new Error('Deployment failed after retries')
  }

  const handleDeploy = async () => {
    setShowConfirmModal(false)
    setIsDeploying(true)
    setDeploymentResult(null)
    setError(null)
    setCancelled(false)
    setBatchResults([])
    setBatchProgress(new Map())
    setCurrentBatch(0)
    setTotalBatches(0)

    const devicesToDeploy = getDeploymentDevices()

    // Calculate rollout percentage
    let rolloutPercent = 100
    if (rolloutStrategy === "25") rolloutPercent = 25
    else if (rolloutStrategy === "50") rolloutPercent = 50
    else if (rolloutStrategy === "custom") rolloutPercent = customPercentage

    const BATCH_SIZE = 7
    const shouldBatch = devicesToDeploy.length > BATCH_SIZE

    try {
      if (shouldBatch) {
        // Batching mode - deploy all batches in parallel
        setIsBatching(true)
        const batches: string[][] = []
        
        // Split devices into batches of 7
        for (let i = 0; i < devicesToDeploy.length; i += BATCH_SIZE) {
          batches.push(devicesToDeploy.slice(i, i + BATCH_SIZE))
        }

        setTotalBatches(batches.length)
        
        // Deploy all batches in parallel
        const batchPromises = batches.map(async (batch, index) => {
          if (cancelled) {
            throw new Error('Deployment cancelled by user')
          }
          
          if (batch.length === 0) {
            return { batchIndex: index, installationIds: [], failedDevices: [], deviceIds: batch }
          }

          try {
            const result = await deployBatchApi(batch, parseInt(apkId), rolloutPercent)
            return { batchIndex: index, ...result, deviceIds: batch }
          } catch (error) {
            // Return failed state for this batch
            return {
              batchIndex: index,
              installationIds: [],
              failedDevices: batch.map(deviceId => ({
                device_id: deviceId,
                alias: devices.find(d => d.id === deviceId)?.alias || 'Unknown',
                reason: error instanceof Error ? error.message : 'Batch deployment failed'
              })),
              deviceIds: batch,
              error
            }
          }
        })

        // Wait for all batches to complete API calls
        const batchResults = await Promise.allSettled(batchPromises)
        
        // Collect all installation IDs and failed devices across all batches
        const allInstallationIds: string[] = []
        const allFailedDevices: any[] = []
        const batchDeviceMap = new Map<number, string[]>() // batch index -> device IDs

        batchResults.forEach((result, index) => {
          if (result.status === 'fulfilled') {
            allInstallationIds.push(...result.value.installationIds)
            allFailedDevices.push(...result.value.failedDevices)
            batchDeviceMap.set(result.value.batchIndex, result.value.deviceIds)
          } else {
            // Handle rejected promise
            const batch = batches[index]
            allFailedDevices.push(...batch.map(deviceId => ({
              device_id: deviceId,
              alias: devices.find(d => d.id === deviceId)?.alias || 'Unknown',
              reason: result.reason?.message || 'Batch deployment failed'
            })))
          }
        })

        // Poll all devices together in a unified loop
        const statusMap = await pollInstallationStatus(allInstallationIds, parseInt(apkId))
        
        // Build results from status map and failed devices
        const deviceMap = new Map(devices.map(d => [d.id, d]))
        const allDetails: Array<{
          device_id: string
          alias: string
          success: boolean
          reason?: string
        }> = []

        // Process successful installations
        statusMap.forEach((statusInfo, deviceId) => {
          const device = deviceMap.get(deviceId)
          const isSuccess = statusInfo.status === 'completed'
          allDetails.push({
            device_id: deviceId,
            alias: device?.alias || 'Unknown',
            success: isSuccess,
            reason: isSuccess ? undefined : (statusInfo.status === 'timeout' ? 'Deployment timeout' : `Status: ${statusInfo.status}`)
          })
        })

        // Process failed devices
        allFailedDevices.forEach((failed: any) => {
          if (!allDetails.find(d => d.device_id === failed.device_id)) {
            allDetails.push({
              device_id: failed.device_id || '',
              alias: failed.alias || 'Unknown',
              success: false,
              reason: failed.reason || 'Unknown error'
            })
          }
        })

        // Create final aggregated result
        const aggregatedResult: DeploymentResult = {
          success: allDetails.filter(d => d.success).length,
          failed: allDetails.filter(d => !d.success).length,
          total: devicesToDeploy.length,
          details: allDetails
        }

        setDeploymentResult(aggregatedResult)
        setIsBatching(false)
      } else {
        // Non-batching mode (7 or fewer devices)
        setIsBatching(false)
        const { installationIds, failedDevices } = await deployBatchApi(
          devicesToDeploy,
          parseInt(apkId),
          rolloutPercent
        )
        
        // Poll for completion
        const statusMap = await pollInstallationStatus(installationIds, parseInt(apkId))
        
        // Build result
        const deviceMap = new Map(devices.map(d => [d.id, d]))
        const details: Array<{
          device_id: string
          alias: string
          success: boolean
          reason?: string
        }> = []

        statusMap.forEach((statusInfo, deviceId) => {
          const device = deviceMap.get(deviceId)
          const isSuccess = statusInfo.status === 'completed'
          details.push({
            device_id: deviceId,
            alias: device?.alias || 'Unknown',
            success: isSuccess,
            reason: isSuccess ? undefined : (statusInfo.status === 'timeout' ? 'Deployment timeout' : `Status: ${statusInfo.status}`)
          })
        })

        failedDevices.forEach((failed: any) => {
          if (!details.find(d => d.device_id === failed.device_id)) {
            details.push({
              device_id: failed.device_id || '',
              alias: failed.alias || 'Unknown',
              success: false,
              reason: failed.reason || 'Unknown error'
            })
          }
        })

        setDeploymentResult({
          success: details.filter(d => d.success).length,
          failed: details.filter(d => !d.success).length,
          total: devicesToDeploy.length,
          details
        })
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Deployment failed')
      console.error('Deployment error:', err)
      setIsBatching(false)
    } finally {
      setIsDeploying(false)
      setCurrentBatch(0)
      setTotalBatches(0)
    }
  }

  const handleCancelDeployment = () => {
    setCancelled(true)
    setIsDeploying(false)
    setIsBatching(false)
    setCurrentBatch(0)
    setTotalBatches(0)
    setBatchProgress(new Map())
    setError('Deployment cancelled by user')
  }

  // Online detection threshold in minutes
  const ONLINE_THRESHOLD_MINUTES = 5

  const formatFileSize = (bytes: number): string => {
    const mb = bytes / (1024 * 1024)
    return `${mb.toFixed(1)} MB`
  }

  const isDeviceOnline = (lastSeen: string): boolean => {
    const lastSeenDate = new Date(lastSeen)
    const now = new Date()
    const diffMinutes = (now.getTime() - lastSeenDate.getTime()) / (1000 * 60)
    return diffMinutes < ONLINE_THRESHOLD_MINUTES
  }

  if (isLoading) {
    return (
      <div className="min-h-screen">
        <Header />
        <main className="mx-auto max-w-[1280px] px-6 pb-12 pt-[84px] md:px-8">
          <div className="py-12 text-center text-muted-foreground">
            Loading...
          </div>
        </main>
      </div>
    )
  }

  if (!apk) {
    return (
      <div className="min-h-screen">
        <Header />
        <main className="mx-auto max-w-[1280px] px-6 pb-12 pt-[84px] md:px-8">
          <div className="py-12 text-center text-muted-foreground">
            APK not found
          </div>
        </main>
      </div>
    )
  }

  return (
    <div className="min-h-screen">
      <Header />

      <main className="mx-auto max-w-[1280px] px-6 pb-12 pt-[84px] md:px-8">
        <div className="mb-6">
          <Button
            variant="ghost"
            onClick={() => router.push('/apk-management')}
            className="gap-2 text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to APK Management
          </Button>
        </div>

        <PageHeader
          icon={<Send className="h-8 w-8" />}
          title="Deploy APK"
          description={`Deploy ${apk.filename} (v${apk.version_name}) to your device fleet`}
        />

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            {/* APK Info Card */}
            <Card className="rounded-2xl border border-border bg-card p-6 shadow-sm">
              <h2 className="mb-4 text-lg font-semibold text-card-foreground">APK Details</h2>
              <div className="grid grid-cols-2 gap-4 text-sm md:grid-cols-4">
                <div>
                  <div className="text-muted-foreground">File Name</div>
                  <div className="font-mono">{apk.filename}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Version</div>
                  <div>{apk.version_name} ({apk.version_code})</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Size</div>
                  <div>{formatFileSize(apk.file_size_bytes)}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Build ID</div>
                  <div>{apk.build_id}</div>
                </div>
              </div>
            </Card>

            {/* Device Selection Card */}
            <Card className="rounded-2xl border border-border bg-card p-6 shadow-sm">
              <div className="mb-4 flex flex-col gap-4">
                <div className="flex items-center justify-between">
                  <h2 className="text-lg font-semibold text-card-foreground">Select Devices</h2>
                  <div className="flex items-center gap-2">
                    <Checkbox
                      id="select-all"
                      checked={filteredDevices.length > 0 && filteredDevices.every(d => selectedDevices.has(d.id))}
                      onCheckedChange={handleSelectAll}
                    />
                    <label htmlFor="select-all" className="text-sm text-muted-foreground cursor-pointer">
                      Select All Filtered ({filteredDevices.length} devices)
                    </label>
                  </div>
                </div>
                
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    placeholder="Filter by device alias (e.g. S, D, Sam...)"
                    value={aliasFilter}
                    onChange={(e) => setAliasFilter(e.target.value)}
                    className="pl-10"
                  />
                  {(aliasFilter || filterOutdatedAgent || filterOutdatedUnity) && (
                    <div className="mt-2 text-xs text-muted-foreground">
                      Showing {filteredDevices.length} of {devices.length} devices
                      {selectedDevices.size > 0 && ` (${selectedDevices.size} selected total)`}
                    </div>
                  )}
                </div>
                
                {/* Version Filters - Contextual based on APK type */}
                {(apkType === 'agent' || apkType === 'unity' || latestAgentVersion || latestUnityVersion) && (
                  <div className="rounded-lg border border-border bg-muted/50 p-4">
                    <div className="mb-3 text-sm font-medium text-card-foreground">Version Filters</div>
                    <div className="space-y-3">
                      {/* Show Agent filter only when deploying Agent APKs or if Agent version is available */}
                      {(apkType === 'agent' || latestAgentVersion) && (
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <Checkbox
                              id="filter-outdated-agent"
                              checked={filterOutdatedAgent}
                              onCheckedChange={(checked) => setFilterOutdatedAgent(checked === true)}
                              disabled={!latestAgentVersion}
                            />
                            <label
                              htmlFor="filter-outdated-agent"
                              className="text-sm cursor-pointer"
                            >
                              Show only devices with outdated Agent version
                            </label>
                          </div>
                          {latestAgentVersion && (
                            <span className="text-xs text-muted-foreground">
                              Latest: {latestAgentVersion}
                            </span>
                          )}
                        </div>
                      )}
                      {/* Show Unity filter only when deploying Unity APKs or if Unity version is available */}
                      {(apkType === 'unity' || latestUnityVersion) && (
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <Checkbox
                              id="filter-outdated-unity"
                              checked={filterOutdatedUnity}
                              onCheckedChange={(checked) => setFilterOutdatedUnity(checked === true)}
                              disabled={!latestUnityVersion}
                            />
                            <label
                              htmlFor="filter-outdated-unity"
                              className="text-sm cursor-pointer"
                            >
                              Show only devices with outdated Unity version
                            </label>
                          </div>
                          {latestUnityVersion && (
                            <span className="text-xs text-muted-foreground">
                              Latest: {latestUnityVersion}
                            </span>
                          )}
                        </div>
                      )}
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
              </div>

              {error && (
                <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-800 dark:bg-red-900/20 dark:text-red-200">
                  {error}
                </div>
              )}

              <div className="space-y-2 max-h-96 overflow-y-auto">
                {filteredDevices.length === 0 ? (
                  <div className="py-8 text-center text-muted-foreground">
                    {devices.length === 0 ? 'No devices found' : 'No devices match your filter'}
                  </div>
                ) : (
                  filteredDevices.map((device) => {
                    const online = isDeviceOnline(device.last_seen)
                    const hasFcmToken = device.fcm_token !== null
                    
                    return (
                      <div
                        key={device.id}
                        className="flex items-center justify-between rounded-lg border border-border p-4"
                      >
                        <div className="flex items-center gap-3">
                          <Checkbox
                            checked={selectedDevices.has(device.id)}
                            onCheckedChange={() => handleToggleDevice(device.id)}
                          />
                          <div>
                            <div className="font-medium">{device.alias}</div>
                            <div className="text-sm text-muted-foreground">
                              {device.id}
                              {!hasFcmToken && <span className="ml-2 text-orange-500">(No FCM token - deployment may fail)</span>}
                            </div>
                          </div>
                        </div>
                        <div className={`text-sm ${online ? 'text-green-600 dark:text-green-400' : 'text-muted-foreground'}`}>
                          {online ? 'Online' : 'Offline'}
                        </div>
                      </div>
                    )
                  })
                )}
              </div>
            </Card>

          {/* Rollout Strategy Card */}
          {selectedDevices.size > 0 && (
            <Card className="rounded-2xl border border-border bg-card p-6 shadow-sm">
              <h2 className="mb-4 text-lg font-semibold text-card-foreground">Rollout Strategy</h2>
              
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                <Button
                  variant={rolloutStrategy === "all" ? "default" : "outline"}
                  onClick={() => setRolloutStrategy("all")}
                  className="h-auto flex-col gap-1 py-3"
                >
                  <div className="text-sm font-semibold">All at Once</div>
                  <div className="text-xs opacity-80">{selectedDevices.size} devices</div>
                </Button>
                <Button
                  variant={rolloutStrategy === "25" ? "default" : "outline"}
                  onClick={() => setRolloutStrategy("25")}
                  className="h-auto flex-col gap-1 py-3"
                >
                  <div className="text-sm font-semibold">Staged 25%</div>
                  <div className="text-xs opacity-80">{Math.ceil((selectedDevices.size * 25) / 100)} devices</div>
                </Button>
                <Button
                  variant={rolloutStrategy === "50" ? "default" : "outline"}
                  onClick={() => setRolloutStrategy("50")}
                  className="h-auto flex-col gap-1 py-3"
                >
                  <div className="text-sm font-semibold">Staged 50%</div>
                  <div className="text-xs opacity-80">{Math.ceil((selectedDevices.size * 50) / 100)} devices</div>
                </Button>
                <Button
                  variant={rolloutStrategy === "custom" ? "default" : "outline"}
                  onClick={() => setRolloutStrategy("custom")}
                  className="h-auto flex-col gap-1 py-3"
                >
                  <div className="text-sm font-semibold">Custom %</div>
                  <div className="text-xs opacity-80">Configure below</div>
                </Button>
              </div>

              {rolloutStrategy === "custom" && (
                <div className="mt-4 rounded-lg border border-border bg-muted p-4">
                  <Label htmlFor="custom-percentage" className="mb-2 block text-sm font-medium">
                    Deployment Percentage
                  </Label>
                  <div className="flex items-center gap-3">
                    <input
                      id="custom-percentage"
                      type="range"
                      min="1"
                      max="100"
                      value={customPercentage}
                      onChange={(e) => setCustomPercentage(parseInt(e.target.value))}
                      className="flex-1"
                    />
                    <div className="w-16 text-right font-mono text-sm font-semibold">
                      {customPercentage}%
                    </div>
                  </div>
                  <div className="mt-2 text-xs text-muted-foreground">
                    Will deploy to {Math.ceil((selectedDevices.size * customPercentage) / 100)} of {selectedDevices.size} selected devices
                  </div>
                </div>
              )}

              {/* Batch Progress Indicator */}
              {isBatching && totalBatches > 0 && (
                <div className="mb-4 rounded-lg border border-blue-200 bg-blue-50 p-4 dark:border-blue-800 dark:bg-blue-900/20">
                  <div className="mb-2 flex items-center justify-between">
                    <div className="text-sm font-medium text-blue-900 dark:text-blue-100">
                      Deploying {totalBatches} batch{totalBatches !== 1 ? 'es' : ''} in parallel
                    </div>
                    <div className="text-xs text-blue-700 dark:text-blue-300">
                      {getDeploymentDevices().length} total devices
                    </div>
                  </div>
                  <div className="mb-2 h-2 w-full overflow-hidden rounded-full bg-blue-200 dark:bg-blue-800">
                    <div
                      className="h-full bg-blue-600 transition-all duration-300 dark:bg-blue-400"
                      style={{ 
                        width: batchProgress.size > 0 
                          ? `${((Array.from(batchProgress.values()).filter(s => s.status === 'completed' || s.status === 'failed' || s.status === 'timeout').length) / getDeploymentDevices().length) * 100}%`
                          : '0%'
                      }}
                    />
                  </div>
                  <div className="mt-2 text-xs text-blue-700 dark:text-blue-300">
                    {batchProgress.size > 0 && (
                      <>
                        {Array.from(batchProgress.values()).filter(s => s.status === 'completed').length} completed,{' '}
                        {Array.from(batchProgress.values()).filter(s => s.status === 'failed' || s.status === 'timeout').length} failed,{' '}
                        {Array.from(batchProgress.values()).filter(s => s.status !== 'completed' && s.status !== 'failed' && s.status !== 'timeout').length} in progress
                      </>
                    )}
                  </div>
                  {batchProgress.size > 0 && (
                    <div className="mt-2 space-y-1">
                      <div className="text-xs font-medium text-blue-900 dark:text-blue-100">
                        Overall Deployment Status:
                      </div>
                      <div className="max-h-32 space-y-1 overflow-y-auto text-xs">
                        {Array.from(batchProgress.entries()).map(([deviceId, statusInfo]) => {
                          const device = devices.find(d => d.id === deviceId)
                          const terminalStatuses = ['completed', 'failed', 'timeout']
                          const isTerminal = terminalStatuses.includes(statusInfo.status)
                          return (
                            <div
                              key={deviceId}
                              className={`flex items-center justify-between rounded px-2 py-1 ${
                                isTerminal
                                  ? statusInfo.status === 'completed'
                                    ? 'bg-green-100 dark:bg-green-900/30'
                                    : 'bg-red-100 dark:bg-red-900/30'
                                  : 'bg-blue-100 dark:bg-blue-900/30'
                              }`}
                            >
                              <span className="truncate">
                                {device?.alias || deviceId.substring(0, 8)}...
                              </span>
                              <span className="ml-2 font-medium">
                                {statusInfo.status === 'completed' ? '✓' :
                                 statusInfo.status === 'failed' ? '✗' :
                                 statusInfo.status === 'timeout' ? '⏱' :
                                 statusInfo.status === 'downloading' ? `↓ ${statusInfo.progress || 0}%` :
                                 statusInfo.status === 'installing' ? '⚙' :
                                 '⏳'}
                              </span>
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  )}
                </div>
              )}

              <div className="mt-6 flex items-center justify-between">
                <div className="text-sm text-muted-foreground">
                  Ready to deploy to {getDeploymentDevices().length} device{getDeploymentDevices().length !== 1 ? 's' : ''}
                  {getDeploymentDevices().length > 7 && !isDeploying && (
                    <span className="ml-2 text-xs text-blue-600 dark:text-blue-400">
                      (Will batch in groups of 7)
                    </span>
                  )}
                </div>
                <div className="flex gap-2">
                  {isDeploying && (
                    <Button
                      onClick={handleCancelDeployment}
                      variant="outline"
                      size="lg"
                      className="gap-2"
                    >
                      <X className="h-4 w-4" />
                      Cancel
                    </Button>
                  )}
                  <Button
                    onClick={handleDeployClick}
                    disabled={selectedDevices.size === 0 || isDeploying}
                    className="gap-2"
                    size="lg"
                  >
                    {isDeploying ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" />
                        {isBatching ? `Deploying ${totalBatches} batch${totalBatches !== 1 ? 'es' : ''} in parallel...` : 'Deploying...'}
                      </>
                    ) : (
                      <>
                        <Send className="h-4 w-4" />
                        Deploy Now
                      </>
                    )}
                  </Button>
                </div>
              </div>
            </Card>
          )}

          {/* Deployment Results */}
          {deploymentResult && (
            <Card className="rounded-2xl border border-border bg-card p-6 shadow-sm">
              <h2 className="mb-4 text-lg font-semibold text-card-foreground">Deployment Results</h2>
              
              <div className="mb-6 grid grid-cols-3 gap-4 text-center">
                <div className="rounded-lg bg-muted p-4">
                  <div className="text-2xl font-bold">{deploymentResult.total}</div>
                  <div className="text-sm text-muted-foreground">Total</div>
                </div>
                <div className="rounded-lg bg-green-50 p-4 dark:bg-green-950">
                  <div className="text-2xl font-bold text-green-600 dark:text-green-400">{deploymentResult.success}</div>
                  <div className="text-sm text-green-600 dark:text-green-400">Success</div>
                </div>
                <div className="rounded-lg bg-red-50 p-4 dark:bg-red-950">
                  <div className="text-2xl font-bold text-red-600 dark:text-red-400">{deploymentResult.failed}</div>
                  <div className="text-sm text-red-600 dark:text-red-400">Failed</div>
                </div>
              </div>

              {/* Detailed Results Table */}
              <div className="mb-6 overflow-hidden rounded-lg border border-border">
                <table className="w-full">
                  <thead className="bg-muted">
                    <tr>
                      <th className="px-4 py-3 text-left text-sm font-semibold text-muted-foreground">Status</th>
                      <th className="px-4 py-3 text-left text-sm font-semibold text-muted-foreground">Device</th>
                      <th className="px-4 py-3 text-left text-sm font-semibold text-muted-foreground">Device ID</th>
                      <th className="px-4 py-3 text-left text-sm font-semibold text-muted-foreground">Result</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {deploymentResult.details.map((detail, idx) => (
                      <tr key={idx} className="hover:bg-muted/50">
                        <td className="px-4 py-3">
                          {detail.success ? (
                            <div className="flex items-center gap-2">
                              <CheckCircle2 className="h-5 w-5 text-green-600 dark:text-green-400" />
                              <span className="text-sm font-medium text-green-600 dark:text-green-400">Success</span>
                            </div>
                          ) : (
                            <div className="flex items-center gap-2">
                              <XCircle className="h-5 w-5 text-red-600 dark:text-red-400" />
                              <span className="text-sm font-medium text-red-600 dark:text-red-400">Failed</span>
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <span className="font-medium text-card-foreground">{detail.alias || 'Unknown'}</span>
                        </td>
                        <td className="px-4 py-3">
                          <span className="font-mono text-xs text-muted-foreground">
                            {detail.device_id ? detail.device_id.substring(0, 8) + '...' : 'N/A'}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          {detail.success ? (
                            <span className="text-sm text-muted-foreground">APK deployed successfully</span>
                          ) : (
                            <span className="text-sm text-red-600 dark:text-red-400">
                              {detail.reason || 'Deployment failed'}
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="flex justify-center gap-3">
                <Button
                  variant="outline"
                  onClick={() => {
                    setDeploymentResult(null)
                    setSelectedDevices(new Set())
                  }}
                >
                  Deploy Another
                </Button>
                <Button
                  onClick={() => router.push('/apk-management')}
                >
                  Back to APK Management
                </Button>
              </div>
            </Card>
          )}
          </div>

          {/* Right Column - Recent Deployments */}
          <div className="lg:col-span-1">
            <Card className="rounded-2xl border border-border bg-card p-6 shadow-sm sticky top-24">
              <div className="flex items-center gap-2 mb-4">
                <Clock className="h-5 w-5 text-muted-foreground" />
                <h2 className="text-lg font-semibold text-card-foreground">Recent Deployments</h2>
              </div>
              
              {loadingRecentDeployments ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              ) : recentDeployments.length === 0 ? (
                <p className="text-sm text-muted-foreground py-4 text-center">No recent deployments</p>
              ) : (
                <div className="space-y-3">
                  {recentDeployments.map((deployment) => (
                    <div
                      key={deployment.id}
                      className="p-3 border rounded-lg hover:bg-muted/50 transition-colors"
                    >
                      <div className="flex items-start justify-between mb-2">
                        <p className="font-medium text-sm truncate flex-1">
                          {deployment.apk?.filename || deployment.apk?.package_name || `APK #${deployment.apk_id}`}
                        </p>
                        <Badge 
                          variant={
                            deployment.status === 'completed' ? 'default' : 
                            deployment.status === 'failed' ? 'destructive' : 
                            'secondary'
                          } 
                          className="ml-2 text-xs"
                        >
                          {deployment.status}
                        </Badge>
                      </div>
                      
                      <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
                        <span className="truncate">
                          {deployment.device?.alias || deployment.device_id?.substring(0, 8) + '...' || 'Unknown Device'}
                        </span>
                      </div>
                      
                      {deployment.apk?.version_name && (
                        <div className="text-xs text-muted-foreground mb-1">
                          v{deployment.apk.version_name}
                        </div>
                      )}
                      
                      <p className="text-xs text-muted-foreground">
                        {new Date(deployment.created_at).toLocaleString()}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>
        </div>
      </main>

      {/* Confirmation Modal */}
      {showConfirmModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <Card className="w-full max-w-md rounded-2xl border border-border bg-card p-6 shadow-xl">
            <h2 className="mb-4 text-xl font-semibold text-card-foreground">Confirm Deployment</h2>
            
            <div className="mb-6 space-y-3 text-sm">
              <div className="flex justify-between rounded-lg bg-muted p-3">
                <span className="text-muted-foreground">APK:</span>
                <span className="font-medium">{apk?.filename}</span>
              </div>
              <div className="flex justify-between rounded-lg bg-muted p-3">
                <span className="text-muted-foreground">Version:</span>
                <span className="font-medium">{apk?.version_name} ({apk?.version_code})</span>
              </div>
              <div className="flex justify-between rounded-lg bg-muted p-3">
                <span className="text-muted-foreground">Strategy:</span>
                <span className="font-medium">
                  {rolloutStrategy === "all" ? "All at Once (100%)" : 
                   rolloutStrategy === "25" ? "Staged Rollout (25%)" :
                   rolloutStrategy === "50" ? "Staged Rollout (50%)" :
                   `Custom Rollout (${customPercentage}%)`}
                </span>
              </div>
              <div className="flex justify-between rounded-lg bg-muted p-3">
                <span className="text-muted-foreground">Devices:</span>
                <span className="font-medium">{getDeploymentDevices().length} of {selectedDevices.size} selected</span>
              </div>
              {getDeploymentDevices().length > 7 && (
                <div className="flex justify-between rounded-lg bg-muted p-3">
                  <span className="text-muted-foreground">Batching:</span>
                  <span className="font-medium">
                    {Math.ceil(getDeploymentDevices().length / 7)} batches of 7 devices
                  </span>
                </div>
              )}
            </div>

            {getDeploymentDevices().length > 7 && (
              <div className="mb-6 rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-200">
                <strong>Batched Deployment:</strong> Devices will be deployed in batches of 7. Each batch must complete before the next batch begins. You can monitor progress in real-time and cancel if needed.
              </div>
            )}

            {rolloutStrategy !== "all" && (
              <div className="mb-6 rounded-lg border border-yellow-200 bg-yellow-50 p-3 text-sm text-yellow-800 dark:border-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-200">
                <strong>Staged Rollout:</strong> Devices will be deployed in order of selection. Monitor results before deploying to remaining devices.
              </div>
            )}

            <div className="flex gap-3">
              <Button
                variant="outline"
                onClick={() => setShowConfirmModal(false)}
                className="flex-1"
              >
                Cancel
              </Button>
              <Button
                onClick={handleDeploy}
                className="flex-1 gap-2"
              >
                <Send className="h-4 w-4" />
                Confirm & Deploy
              </Button>
            </div>
          </Card>
        </div>
      )}
    </div>
  )
}
