"use client"

import { useState, useEffect } from "react"
import { useParams, useRouter } from "next/navigation"
import { Header } from "@/components/header"
import { PageHeader } from "@/components/page-header"
import { ArrowLeft, Send, CheckCircle2, XCircle, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { isAuthenticated } from "@/lib/api-client"

interface Device {
  id: string
  alias: string
  fcm_token: string | null
  last_seen: string
  status: "online" | "offline"
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

export default function ApkDeployPage() {
  const params = useParams()
  const router = useRouter()
  const apkId = params.apk_id as string
  
  const [isDark, setIsDark] = useState(false)
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
  const [authChecked, setAuthChecked] = useState(false)

  // Check authentication
  useEffect(() => {
    if (!isAuthenticated()) {
      router.push('/login')
    } else {
      setAuthChecked(true)
    }
  }, [router])

  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add("dark")
    } else {
      document.documentElement.classList.remove("dark")
    }
  }, [isDark])

  useEffect(() => {
    if (authChecked) {
      fetchData()
    }
  }, [apkId, authChecked])

  const fetchData = async () => {
    setIsLoading(true)
    setError(null)
    
    try {
      // Get auth token from localStorage
      const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null
      
      if (!token) {
        throw new Error('Authentication required')
      }

      // Fetch APK details and devices in parallel
      const [apkRes, devicesRes] = await Promise.all([
        fetch(`/admin/apk/builds?limit=100&order=desc`),
        fetch('/api/proxy/v1/devices', {
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

      // Find the specific APK by build_id
      const targetApk = apkData.builds?.find((b: ApkBuild) => b.build_id === parseInt(apkId))
      
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

  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      const allDeviceIds = devices
        .filter(d => d.fcm_token)
        .map(d => d.id)
      setSelectedDevices(new Set(allDeviceIds))
    } else {
      setSelectedDevices(new Set())
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

  const handleDeploy = async () => {
    setShowConfirmModal(false)
    setIsDeploying(true)
    setDeploymentResult(null)
    setError(null)

    const devicesToDeploy = getDeploymentDevices()

    try {
      const response = await fetch('/v1/apk/deploy', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          apk_id: parseInt(apkId),
          device_ids: devicesToDeploy
        })
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || 'Deployment failed')
      }

      const result = await response.json()
      setDeploymentResult({
        success: result.success_count || 0,
        failed: result.failed_devices?.length || 0,
        total: devicesToDeploy.length,
        details: [
          ...(result.installations || []).map((inst: any) => ({
            device_id: inst.device?.id || '',
            alias: inst.device?.alias || '',
            success: true
          })),
          ...(result.failed_devices || []).map((failed: any) => ({
            device_id: failed.device_id || '',
            alias: failed.alias || '',
            success: false,
            reason: failed.reason || 'Unknown error'
          }))
        ]
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Deployment failed')
      console.error('Deployment error:', err)
    } finally {
      setIsDeploying(false)
    }
  }

  const formatFileSize = (bytes: number): string => {
    const mb = bytes / (1024 * 1024)
    return `${mb.toFixed(1)} MB`
  }

  const isDeviceOnline = (lastSeen: string): boolean => {
    const lastSeenDate = new Date(lastSeen)
    const now = new Date()
    const diffMinutes = (now.getTime() - lastSeenDate.getTime()) / (1000 * 60)
    return diffMinutes < 5 // Consider online if seen in last 5 minutes
  }

  if (isLoading) {
    return (
      <div className="min-h-screen">
        <Header isDark={isDark} onToggleDark={() => setIsDark(!isDark)} />
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
        <Header isDark={isDark} onToggleDark={() => setIsDark(!isDark)} />
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
      <Header isDark={isDark} onToggleDark={() => setIsDark(!isDark)} />

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

        <div className="space-y-6">
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
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-card-foreground">Select Devices</h2>
              <div className="flex items-center gap-2">
                <Checkbox
                  id="select-all"
                  checked={selectedDevices.size === devices.filter(d => d.fcm_token).length && devices.length > 0}
                  onCheckedChange={handleSelectAll}
                />
                <label htmlFor="select-all" className="text-sm text-muted-foreground cursor-pointer">
                  Select All ({devices.filter(d => d.fcm_token).length} devices)
                </label>
              </div>
            </div>

            {error && (
              <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-800 dark:bg-red-900/20 dark:text-red-200">
                {error}
              </div>
            )}

            <div className="space-y-2 max-h-96 overflow-y-auto">
              {devices.length === 0 ? (
                <div className="py-8 text-center text-muted-foreground">
                  No devices found
                </div>
              ) : (
                devices.map((device) => {
                  const online = isDeviceOnline(device.last_seen)
                  const canDeploy = device.fcm_token !== null
                  
                  return (
                    <div
                      key={device.id}
                      className={`flex items-center justify-between rounded-lg border border-border p-4 ${
                        !canDeploy ? 'opacity-50' : ''
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <Checkbox
                          checked={selectedDevices.has(device.id)}
                          onCheckedChange={() => handleToggleDevice(device.id)}
                          disabled={!canDeploy}
                        />
                        <div>
                          <div className="font-medium">{device.alias}</div>
                          <div className="text-sm text-muted-foreground">
                            {device.id}
                            {!canDeploy && <span className="ml-2 text-red-500">(No FCM token)</span>}
                          </div>
                        </div>
                      </div>
                      <div className={`text-sm ${online ? 'text-green-600 dark:text-green-400' : 'text-muted-foreground'}`}>
                        {online ? '● Online' : '○ Offline'}
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

              <div className="mt-6 flex items-center justify-between">
                <div className="text-sm text-muted-foreground">
                  Ready to deploy to {getDeploymentDevices().length} device{getDeploymentDevices().length !== 1 ? 's' : ''}
                </div>
                <Button
                  onClick={handleDeployClick}
                  disabled={selectedDevices.size === 0 || isDeploying}
                  className="gap-2"
                  size="lg"
                >
                  {isDeploying ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Deploying...
                    </>
                  ) : (
                    <>
                      <Send className="h-4 w-4" />
                      Deploy Now
                    </>
                  )}
                </Button>
              </div>
            </Card>
          )}

          {/* Deployment Results */}
          {deploymentResult && (
            <Card className="rounded-2xl border border-border bg-card p-6 shadow-sm">
              <h2 className="mb-4 text-lg font-semibold text-card-foreground">Deployment Results</h2>
              
              <div className="mb-4 grid grid-cols-3 gap-4 text-center">
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

              <div className="space-y-2">
                {deploymentResult.details.map((detail, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between rounded-lg border border-border p-3"
                  >
                    <div className="flex items-center gap-2">
                      {detail.success ? (
                        <CheckCircle2 className="h-5 w-5 text-green-600 dark:text-green-400" />
                      ) : (
                        <XCircle className="h-5 w-5 text-red-600 dark:text-red-400" />
                      )}
                      <div>
                        <div className="font-medium">{detail.alias}</div>
                        {detail.reason && (
                          <div className="text-sm text-muted-foreground">{detail.reason}</div>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              <div className="mt-4 text-center">
                <Button
                  variant="outline"
                  onClick={() => router.push('/apk-management')}
                >
                  Back to APK Management
                </Button>
              </div>
            </Card>
          )}
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
            </div>

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
