"use client"

import { useState, useEffect } from "react"
import { useParams, useRouter } from "next/navigation"
import { Header } from "@/components/header"
import { PageHeader } from "@/components/page-header"
import { ArrowLeft, Send, CheckCircle2, XCircle, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"

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

  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add("dark")
    } else {
      document.documentElement.classList.remove("dark")
    }
  }, [isDark])

  useEffect(() => {
    fetchData()
  }, [apkId])

  const fetchData = async () => {
    setIsLoading(true)
    setError(null)
    
    try {
      // Fetch APK details and devices in parallel
      const [apkRes, devicesRes] = await Promise.all([
        fetch(`/admin/apk/builds?build_id=${apkId}`),
        fetch('/v1/devices')
      ])

      if (!apkRes.ok || !devicesRes.ok) {
        throw new Error('Failed to fetch data')
      }

      const apkData = await apkRes.json()
      const devicesData = await devicesRes.json()

      if (apkData.builds && apkData.builds.length > 0) {
        setApk(apkData.builds[0])
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

  const handleDeploy = async () => {
    if (selectedDevices.size === 0) {
      alert('Please select at least one device')
      return
    }

    setIsDeploying(true)
    setDeploymentResult(null)
    setError(null)

    try {
      const response = await fetch('/v1/apk/deploy', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          apk_id: parseInt(apkId),
          device_ids: Array.from(selectedDevices)
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
        total: selectedDevices.size,
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

            <div className="mt-6 flex items-center justify-between">
              <div className="text-sm text-muted-foreground">
                {selectedDevices.size} device{selectedDevices.size !== 1 ? 's' : ''} selected
              </div>
              <Button
                onClick={handleDeploy}
                disabled={selectedDevices.size === 0 || isDeploying}
                className="gap-2"
              >
                {isDeploying ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Deploying...
                  </>
                ) : (
                  <>
                    <Send className="h-4 w-4" />
                    Deploy to {selectedDevices.size} Device{selectedDevices.size !== 1 ? 's' : ''}
                  </>
                )}
              </Button>
            </div>
          </Card>

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
    </div>
  )
}
