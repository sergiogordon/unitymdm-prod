"use client"

import { useState, useEffect, useRef } from "react"
import { Send, CheckCircle2, Loader2, X } from "lucide-react"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { toast } from "sonner"

interface ApkDeployDialogProps {
  isOpen: boolean
  onClose: () => void
  apk: {
    id: number
    package_name: string
    version_name: string
    version_code: number
  }
  onDeployComplete: () => void
}

interface Device {
  id: string
  alias: string
  status: string
  model?: string
}

interface InstallationProgress {
  device_id: string
  status: string
  progress: number
}

export function ApkDeployDialog({ isOpen, onClose, apk, onDeployComplete }: ApkDeployDialogProps) {
  const [devices, setDevices] = useState<Device[]>([])
  const [selectedDeviceIds, setSelectedDeviceIds] = useState<Set<string>>(new Set())
  const [isLoading, setIsLoading] = useState(true)
  const [isDeploying, setIsDeploying] = useState(false)
  const [installationProgress, setInstallationProgress] = useState<Map<string, InstallationProgress>>(new Map())
  const [activeInstallationIds, setActiveInstallationIds] = useState<number[]>([])
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null)

  useEffect(() => {
    if (isOpen) {
      loadDevices()
    }
  }, [isOpen])

  // Poll for installation progress when deploying
  useEffect(() => {
    if (isDeploying && activeInstallationIds.length > 0) {
      const pollProgress = async () => {
        try {
          const token = localStorage.getItem('auth_token')
          const response = await fetch(`/v1/apk/installations?apk_id=${apk.id}`, {
            headers: {
              'Authorization': `Bearer ${token}`
            }
          })
          if (response.ok) {
            const installations = await response.json()
            
            activeInstallationIds.forEach((installationId) => {
              const installation = installations.find((i: any) => i.id === installationId)
              if (installation) {
                setInstallationProgress((prev) => {
                  const newMap = new Map(prev)
                  newMap.set(installation.device_id, {
                    device_id: installation.device_id,
                    status: installation.status,
                    progress: installation.download_progress || 0,
                  })
                  return newMap
                })
              }
            })
            
            // Check if all completed (including timeout as a terminal state)
            const terminalStatuses = ['completed', 'failed', 'timeout']
            const allCompleted = activeInstallationIds.every((installationId) => {
              const installation = installations.find((i: any) => i.id === installationId)
              return installation && terminalStatuses.includes(installation.status)
            })
            
            if (allCompleted) {
              pollingIntervalRef.current && clearInterval(pollingIntervalRef.current)
              pollingIntervalRef.current = null
              
              setTimeout(() => {
                setIsDeploying(false)
                const failedCount = installations.filter((i: any) => 
                  activeInstallationIds.includes(i.id) && (i.status === 'failed' || i.status === 'timeout')
                ).length
                const successCount = installations.filter((i: any) => 
                  activeInstallationIds.includes(i.id) && i.status === 'completed'
                ).length
                
                if (failedCount === 0) {
                  toast.success(`All ${successCount} deployment(s) completed successfully`)
                } else if (successCount === 0) {
                  toast.error(`All ${failedCount} deployment(s) failed or timed out`)
                } else {
                  toast.warning(`${successCount} succeeded, ${failedCount} failed/timed out`)
                }
                
                onDeployComplete()
              }, 1500)
            }
          }
        } catch (error) {
          console.error('[DEPLOY] Failed to poll progress:', error)
        }
      }
      
      // Poll immediately, then every second
      pollProgress()
      pollingIntervalRef.current = setInterval(pollProgress, 1000)
      
      return () => {
        if (pollingIntervalRef.current) {
          clearInterval(pollingIntervalRef.current)
          pollingIntervalRef.current = null
        }
      }
    }
  }, [isDeploying, activeInstallationIds, apk.id])

  const loadDevices = async () => {
    try {
      const token = localStorage.getItem('auth_token')
      const response = await fetch('/v1/devices?page=1&limit=200', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      })
      if (response.ok) {
        const data = await response.json()
        setDevices(data.devices)
      }
    } catch (error) {
      console.error('Failed to load devices:', error)
    } finally {
      setIsLoading(false)
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
    if (selectedDeviceIds.size === devices.length) {
      setSelectedDeviceIds(new Set())
    } else {
      setSelectedDeviceIds(new Set(devices.map((d) => d.id)))
    }
  }

  const handleDeploy = async () => {
    if (selectedDeviceIds.size === 0) {
      toast.error('Please select at least one device')
      return
    }

    setIsDeploying(true)
    setInstallationProgress(new Map())

    try {
      const token = localStorage.getItem('auth_token')
      const response = await fetch('/v1/apk/deploy', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          apk_id: apk.id,
          device_ids: Array.from(selectedDeviceIds),
        }),
      })

      const result = await response.json()

      if (response.ok) {
        // Store installation IDs for polling
        if (result.installation_ids && result.installation_ids.length > 0) {
          setActiveInstallationIds(result.installation_ids)
        }
        
        toast.success(`Deployment initiated for ${result.success_count} device(s)`)
        if (result.failed_count > 0) {
          toast.warning(`${result.failed_count} device(s) failed to receive deployment`)
        }
        
        // If no successful deployments, stop deploying state
        if (result.success_count === 0) {
          setIsDeploying(false)
        }
      } else {
        toast.error(result.error || 'Failed to deploy APK')
        setIsDeploying(false)
      }
    } catch (error) {
      toast.error('Failed to deploy APK')
      setIsDeploying(false)
    }
  }

  const handleClose = () => {
    // Prevent closing while deploying
    if (isDeploying) {
      toast.info('Please wait for deployment to complete')
      return
    }
    setSelectedDeviceIds(new Set())
    setIsDeploying(false)
    setInstallationProgress(new Map())
    onClose()
  }

  const getDeviceStatus = (deviceId: string) => {
    const progress = installationProgress.get(deviceId)
    if (!progress) {
      if (isDeploying && selectedDeviceIds.has(deviceId)) {
        return (
          <div className="flex items-center gap-2 text-sm">
            <Loader2 className="h-3.5 w-3.5 animate-spin text-gray-400" />
            <span className="text-gray-400">Waiting...</span>
          </div>
        )
      }
      return null
    }

    switch (progress.status) {
      case 'pending':
        return (
          <div className="flex items-center gap-2 text-sm">
            <Loader2 className="h-3.5 w-3.5 animate-spin text-gray-400" />
            <span className="text-gray-400">Pending...</span>
          </div>
        )
      case 'downloading':
        return (
          <div className="flex items-center gap-2 text-sm">
            <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-500" />
            <span className="text-blue-500">Downloading {progress.progress}%</span>
          </div>
        )
      case 'installing':
        return (
          <div className="flex items-center gap-2 text-sm">
            <Loader2 className="h-3.5 w-3.5 animate-spin text-orange-500" />
            <span className="text-orange-500">Installing...</span>
          </div>
        )
      case 'completed':
        return (
          <div className="flex items-center gap-2 text-sm">
            <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
            <span className="text-green-500">Completed</span>
          </div>
        )
      case 'failed':
        return (
          <div className="flex items-center gap-2 text-sm">
            <X className="h-3.5 w-3.5 text-red-500" />
            <span className="text-red-500">Failed</span>
          </div>
        )
      case 'timeout':
        return (
          <div className="flex items-center gap-2 text-sm">
            <X className="h-3.5 w-3.5 text-yellow-500" />
            <span className="text-yellow-500">Timeout</span>
          </div>
        )
      default:
        return (
          <div className="flex items-center gap-2 text-sm">
            <Loader2 className="h-3.5 w-3.5 animate-spin text-gray-400" />
            <span className="text-gray-400">{progress.status}</span>
          </div>
        )
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[600px]" onPointerDownOutside={(e) => {
        if (isDeploying) {
          e.preventDefault()
          toast.info('Please wait for deployment to complete')
        }
      }} onEscapeKeyDown={(e) => {
        if (isDeploying) {
          e.preventDefault()
          toast.info('Please wait for deployment to complete')
        }
      }}>
        <DialogHeader>
          <DialogTitle>Deploy APK</DialogTitle>
          <div className="mt-2 text-sm text-muted-foreground">
            {apk.package_name} v{apk.version_name} ({apk.version_code})
          </div>
        </DialogHeader>

        <div className="max-h-[400px] space-y-2 overflow-y-auto py-4">
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
            </div>
          ) : devices.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              No devices available
            </div>
          ) : (
            <>
              <div className="flex items-center gap-2 border-b border-border pb-2">
                <Checkbox
                  checked={selectedDeviceIds.size === devices.length && devices.length > 0}
                  onCheckedChange={handleToggleAll}
                  disabled={isDeploying}
                />
                <span className="text-sm font-medium">
                  Select All ({selectedDeviceIds.size}/{devices.length})
                </span>
              </div>
              {devices.map((device) => (
                <div
                  key={device.id}
                  className="flex items-center justify-between rounded-lg border border-border p-3 transition-colors hover:bg-muted/30"
                >
                  <div className="flex items-center gap-3">
                    <Checkbox
                      checked={selectedDeviceIds.has(device.id)}
                      onCheckedChange={() => handleToggleDevice(device.id)}
                      disabled={isDeploying}
                    />
                    <div>
                      <div className="font-medium">{device.alias}</div>
                      {device.model && (
                        <div className="text-xs text-muted-foreground">{device.model}</div>
                      )}
                    </div>
                  </div>
                  {getDeviceStatus(device.id)}
                </div>
              ))}
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={handleClose} disabled={isDeploying}>
            {isDeploying ? 'Close' : 'Cancel'}
          </Button>
          <Button onClick={handleDeploy} disabled={isDeploying || selectedDeviceIds.size === 0}>
            {isDeploying ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Deploying...
              </>
            ) : (
              <>
                <Send className="mr-2 h-4 w-4" />
                Deploy to {selectedDeviceIds.size} device(s)
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
