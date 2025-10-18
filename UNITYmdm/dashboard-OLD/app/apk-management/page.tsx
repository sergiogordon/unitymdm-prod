"use client"

import { useState, useEffect } from "react"
import { Upload, Package, Trash2, Send, Download, TrendingUp, RotateCcw, Settings2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Header } from "@/components/header"
import { Sidebar } from "@/components/sidebar"
import { ProtectedLayout } from "@/components/protected-layout"
import { ApkUploadDialog } from "@/components/apk-upload-dialog"
import { ApkDeployDialog } from "@/components/apk-deploy-dialog"
import { toast } from "sonner"
import { formatAbsoluteTimestampCST } from "@/lib/utils"
import { SettingsDrawer } from "@/components/settings-drawer"
import { isDemoMode } from "@/lib/demoUtils"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Slider } from "@/components/ui/slider"
import { Checkbox } from "@/components/ui/checkbox"
import { Label } from "@/components/ui/label"

interface ApkVersion {
  id: number
  package_name: string
  version_name: string
  version_code: number
  file_size: number
  uploaded_at: string
  uploaded_by: string
  is_current?: boolean
  staged_rollout_percent?: number
  promoted_at?: string | null
  promoted_by?: string | null
  wifi_only?: boolean
  must_install?: boolean
  signer_fingerprint?: string | null
  deployment_stats?: {
    total_deployments: number
    last_deployed_at: string | null
    deployed_devices: number
    adoption_rate?: number
    total_checks?: number
    total_eligible?: number
    installs_success?: number
    installs_failed?: number
  }
}

export default function ApkManagementPage() {
  return (
    <ProtectedLayout>
      <ApkManagementContent />
    </ProtectedLayout>
  )
}

function ApkManagementContent() {
  const [isDark, setIsDark] = useState(false)
  const [isSidebarOpen, setIsSidebarOpen] = useState(true)
  const [lastUpdated, setLastUpdated] = useState(Date.now())
  const [apkVersions, setApkVersions] = useState<ApkVersion[]>([])
  const [isUploadDialogOpen, setIsUploadDialogOpen] = useState(false)
  const [selectedApk, setSelectedApk] = useState<ApkVersion | null>(null)
  const [isDeployDialogOpen, setIsDeployDialogOpen] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  
  // OTA dialog states
  const [isPromoteDialogOpen, setIsPromoteDialogOpen] = useState(false)
  const [isRolloutDialogOpen, setIsRolloutDialogOpen] = useState(false)
  const [isRollbackDialogOpen, setIsRollbackDialogOpen] = useState(false)

  useEffect(() => {
    const isDarkMode = localStorage.getItem('darkMode') === 'true'
    setIsDark(isDarkMode)
  }, [])

  useEffect(() => {
    const sidebarOpen = localStorage.getItem('sidebarOpen')
    if (sidebarOpen !== null) {
      setIsSidebarOpen(sidebarOpen === 'true')
    }
  }, [])

  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add("dark")
    } else {
      document.documentElement.classList.remove("dark")
    }
  }, [isDark])

  useEffect(() => {
    loadApkVersions()
  }, [])

  const loadApkVersions = async () => {
    try {
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), 10000)
      
      // Get JWT token from localStorage
      const token = localStorage.getItem('access_token')
      const headers: HeadersInit = {}
      if (token) {
        headers['Authorization'] = `Bearer ${token}`
      }
      
      const response = await fetch('/v1/apk/list', { 
        signal: controller.signal,
        headers
      })
      clearTimeout(timeoutId)
      
      if (response.ok) {
        const apks = await response.json()
        
        // Fetch deployment stats for each APK
        const apksWithStats = await Promise.all(apks.map(async (apk: ApkVersion) => {
          try {
            const statsResponse = await fetch(`/v1/apk/installations?apk_id=${apk.id}`, {
              headers
            })
            if (statsResponse.ok) {
              const installations = await statsResponse.json()
              const total = installations.length
              const deviceIds = new Set(installations.map((i: any) => i.device_id))
              const lastDeployed = installations.length > 0 ? installations[0].initiated_at : null
              
              return {
                ...apk,
                deployment_stats: {
                  total_deployments: total,
                  last_deployed_at: lastDeployed,
                  deployed_devices: deviceIds.size,
                  adoption_rate: apk.deployment_stats?.adoption_rate,
                  total_checks: apk.deployment_stats?.total_checks,
                  total_eligible: apk.deployment_stats?.total_eligible,
                  installs_success: apk.deployment_stats?.installs_success,
                  installs_failed: apk.deployment_stats?.installs_failed,
                }
              }
            }
          } catch (err) {
            console.error('Failed to load deployment stats:', err)
          }
          return apk
        }))
        
        setApkVersions(apksWithStats)
        setLastUpdated(Date.now())
      } else {
        toast.error('Failed to load APK list')
      }
    } catch (error) {
      console.error('Failed to load APK versions:', error)
      toast.error('Failed to load APK list - request timeout')
    } finally {
      setIsLoading(false)
    }
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

  const handleUploadComplete = () => {
    setIsUploadDialogOpen(false)
    loadApkVersions()
    toast.success('APK uploaded successfully')
  }

  const handleDeployClick = (apk: ApkVersion) => {
    setSelectedApk(apk)
    setIsDeployDialogOpen(true)
  }

  const handleDeployComplete = () => {
    loadApkVersions() // Refresh APK list to show updated deployment stats
    setIsDeployDialogOpen(false)
    setSelectedApk(null)
  }

  const handleDeleteApk = async (apkId: number) => {
    if (!confirm('Are you sure you want to delete this APK version?')) return

    try {
      const token = localStorage.getItem('access_token')
      console.log('[APK DELETE DEBUG] Token from localStorage:', token ? `${token.substring(0, 20)}...` : 'NULL')
      console.log('[APK DELETE DEBUG] Deleting APK ID:', apkId)
      
      const response = await fetch(`/v1/apk/${apkId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })

      console.log('[APK DELETE DEBUG] Response status:', response.status)
      
      if (response.ok) {
        toast.success('APK deleted successfully')
        loadApkVersions()
      } else {
        const error = await response.json()
        console.log('[APK DELETE DEBUG] Error response:', error)
        toast.error(error.error || error.detail || 'Failed to delete APK')
      }
    } catch (error) {
      console.error('[APK DELETE DEBUG] Exception:', error)
      toast.error('Failed to delete APK')
    }
  }

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const handleDownloadApk = async (apkId: number, packageName: string, versionCode: number) => {
    // Demo mode check
    if (isDemoMode()) {
      toast.info('Nothing to download in demo mode')
      return
    }

    try {
      // Download the APK file
      const response = await fetch(`/v1/apk/download-web/${apkId}`)
      
      if (!response.ok) {
        throw new Error('Failed to download APK')
      }

      // Get the blob from the response
      const blob = await response.blob()
      
      // Create a temporary URL for the blob
      const url = window.URL.createObjectURL(blob)
      
      // Create a temporary anchor element and trigger download
      const a = document.createElement('a')
      a.href = url
      a.download = `${packageName}_${versionCode}.apk`
      document.body.appendChild(a)
      a.click()
      
      // Cleanup
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
      
      toast.success('APK download started')
    } catch (error) {
      console.error('Failed to download APK:', error)
      toast.error('Failed to download APK')
    }
  }

  const handlePromoteClick = (apk: ApkVersion) => {
    setSelectedApk(apk)
    setIsPromoteDialogOpen(true)
  }

  const handleAdjustRolloutClick = (apk: ApkVersion) => {
    setSelectedApk(apk)
    setIsRolloutDialogOpen(true)
  }

  const handleRollbackClick = (apk: ApkVersion) => {
    setSelectedApk(apk)
    setIsRollbackDialogOpen(true)
  }

  const currentApk = apkVersions.find(apk => apk.is_current)

  return (
    <div className="min-h-screen">
      <Sidebar isOpen={isSidebarOpen} onToggle={handleToggleSidebar} />
      
      <Header
        lastUpdated={lastUpdated}
        alertCount={0}
        isDark={isDark}
        onToggleDark={handleToggleDark}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onRefresh={loadApkVersions}
        onToggleSidebar={handleToggleSidebar}
      />

      <main className={`transition-all duration-300 px-6 pb-12 pt-[84px] md:px-8 ${isSidebarOpen ? 'lg:ml-64' : 'lg:ml-16'}`}>
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">APK Management</h2>
            <p className="mt-1 text-sm text-muted-foreground">Upload and deploy APK files to your fleet</p>
          </div>
          <Button onClick={() => setIsUploadDialogOpen(true)} className="gap-2">
            <Upload className="h-4 w-4" />
            Upload APK
          </Button>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
          </div>
        ) : apkVersions.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border bg-muted/30 p-12 text-center">
            <Package className="mx-auto h-12 w-12 text-muted-foreground" />
            <h3 className="mt-4 text-lg font-medium">No APK files uploaded</h3>
            <p className="mt-2 text-sm text-muted-foreground">
              Upload your first APK to deploy it to your devices
            </p>
            <Button onClick={() => setIsUploadDialogOpen(true)} className="mt-6 gap-2">
              <Upload className="h-4 w-4" />
              Upload APK
            </Button>
          </div>
        ) : (
          <div className="overflow-hidden rounded-lg border border-border bg-card">
            <table className="w-full">
              <thead className="border-b border-border bg-muted/50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    Package
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    Version
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    Size
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    Uploaded
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    Uploaded By
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    Deployment Stats
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {apkVersions.map((apk) => (
                  <tr key={apk.id} className="hover:bg-muted/30 transition-colors">
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
                          <Package className="h-5 w-5 text-primary" />
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-medium">{apk.package_name}</span>
                            {apk.is_current && (
                              <Badge className="bg-green-500 hover:bg-green-500 text-white border-green-600">
                                Current
                              </Badge>
                            )}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="text-sm">
                        <div>{apk.version_name}</div>
                        <div className="text-muted-foreground">Code: {apk.version_code}</div>
                        {apk.staged_rollout_percent !== undefined && apk.staged_rollout_percent !== null && (
                          <div className="text-xs text-blue-600 dark:text-blue-400">
                            Rollout: {apk.staged_rollout_percent}%
                          </div>
                        )}
                      </div>
                    </td>
                    <td className="px-6 py-4 text-sm">
                      {formatFileSize(apk.file_size)}
                    </td>
                    <td className="px-6 py-4 text-sm text-muted-foreground">
                      {formatAbsoluteTimestampCST(apk.uploaded_at)}
                    </td>
                    <td className="px-6 py-4 text-sm">
                      {apk.uploaded_by}
                    </td>
                    <td className="px-6 py-4">
                      {apk.deployment_stats ? (
                        <div className="text-sm">
                          {apk.deployment_stats.last_deployed_at ? (
                            <>
                              <div className="text-muted-foreground text-xs">
                                {formatAbsoluteTimestampCST(apk.deployment_stats.last_deployed_at)}
                              </div>
                              <div className="text-xs text-muted-foreground">
                                {apk.deployment_stats.deployed_devices} device{apk.deployment_stats.deployed_devices !== 1 ? 's' : ''} · {apk.deployment_stats.total_deployments} deployment{apk.deployment_stats.total_deployments !== 1 ? 's' : ''}
                              </div>
                              {(apk.deployment_stats.adoption_rate !== undefined || 
                                apk.deployment_stats.installs_success !== undefined) && (
                                <div className="text-xs text-green-600 dark:text-green-400 mt-1">
                                  {apk.deployment_stats.adoption_rate !== undefined && (
                                    <div>Adoption: {apk.deployment_stats.adoption_rate.toFixed(1)}%</div>
                                  )}
                                  {apk.deployment_stats.installs_success !== undefined && (
                                    <div>
                                      ✓ {apk.deployment_stats.installs_success} 
                                      {apk.deployment_stats.installs_failed ? ` / ✗ ${apk.deployment_stats.installs_failed}` : ''}
                                    </div>
                                  )}
                                </div>
                              )}
                            </>
                          ) : (
                            <span className="text-muted-foreground">Never deployed</span>
                          )}
                        </div>
                      ) : (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center justify-end gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleDownloadApk(apk.id, apk.package_name, apk.version_code)}
                          className="gap-2"
                        >
                          <Download className="h-3.5 w-3.5" />
                          Download
                        </Button>
                        <Button
                          size="sm"
                          onClick={() => handleDeployClick(apk)}
                          className="gap-2"
                        >
                          <Send className="h-3.5 w-3.5" />
                          Deploy
                        </Button>
                        
                        {/* OTA Management Buttons */}
                        {apk.is_current ? (
                          <>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => handleAdjustRolloutClick(apk)}
                              className="gap-2"
                            >
                              <Settings2 className="h-3.5 w-3.5" />
                              Adjust Rollout
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => handleRollbackClick(apk)}
                              className="gap-2 text-orange-600 hover:text-orange-700"
                            >
                              <RotateCcw className="h-3.5 w-3.5" />
                              Rollback
                            </Button>
                          </>
                        ) : (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handlePromoteClick(apk)}
                            className="gap-2"
                          >
                            <TrendingUp className="h-3.5 w-3.5" />
                            Promote
                          </Button>
                        )}
                        
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleDeleteApk(apk.id)}
                        >
                          <Trash2 className="h-3.5 w-3.5 text-destructive" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>

      <ApkUploadDialog
        isOpen={isUploadDialogOpen}
        onClose={() => setIsUploadDialogOpen(false)}
        onUploadComplete={handleUploadComplete}
      />

      {selectedApk && (
        <ApkDeployDialog
          isOpen={isDeployDialogOpen}
          onClose={() => {
            setIsDeployDialogOpen(false)
            setSelectedApk(null)
          }}
          apk={selectedApk}
          onDeployComplete={handleDeployComplete}
        />
      )}

      {selectedApk && (
        <PromoteDialog
          isOpen={isPromoteDialogOpen}
          onClose={() => {
            setIsPromoteDialogOpen(false)
            setSelectedApk(null)
          }}
          apk={selectedApk}
          onPromoteComplete={() => {
            loadApkVersions()
            setIsPromoteDialogOpen(false)
            setSelectedApk(null)
          }}
        />
      )}

      {selectedApk && (
        <RolloutDialog
          isOpen={isRolloutDialogOpen}
          onClose={() => {
            setIsRolloutDialogOpen(false)
            setSelectedApk(null)
          }}
          apk={selectedApk}
          onRolloutComplete={() => {
            loadApkVersions()
            setIsRolloutDialogOpen(false)
            setSelectedApk(null)
          }}
        />
      )}

      {selectedApk && currentApk && (
        <RollbackDialog
          isOpen={isRollbackDialogOpen}
          onClose={() => {
            setIsRollbackDialogOpen(false)
            setSelectedApk(null)
          }}
          currentApk={currentApk}
          apkVersions={apkVersions}
          onRollbackComplete={() => {
            loadApkVersions()
            setIsRollbackDialogOpen(false)
            setSelectedApk(null)
          }}
        />
      )}

      <SettingsDrawer
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
      />
    </div>
  )
}

// PromoteDialog Component
function PromoteDialog({
  isOpen,
  onClose,
  apk,
  onPromoteComplete,
}: {
  isOpen: boolean
  onClose: () => void
  apk: ApkVersion
  onPromoteComplete: () => void
}) {
  const [rolloutPercent, setRolloutPercent] = useState([10])
  const [wifiOnly, setWifiOnly] = useState(false)
  const [mustInstall, setMustInstall] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const rolloutOptions = [1, 5, 10, 25, 50, 100]

  const handlePromote = async () => {
    setIsSubmitting(true)
    try {
      const token = localStorage.getItem('access_token')
      const response = await fetch(`/v1/apk/${apk.id}/promote`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          staged_rollout_percent: rolloutPercent[0],
          wifi_only: wifiOnly,
          must_install: mustInstall,
        }),
      })

      if (response.ok) {
        toast.success(`Promoted ${apk.package_name} to ${rolloutPercent[0]}% rollout`)
        onPromoteComplete()
      } else {
        const error = await response.json()
        toast.error(error.error || error.detail || 'Failed to promote APK')
      }
    } catch (error) {
      console.error('Failed to promote APK:', error)
      toast.error('Failed to promote APK')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Promote APK to Current</DialogTitle>
          <DialogDescription>
            Promote {apk.package_name} v{apk.version_name} as the current version for OTA updates
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          <div className="space-y-4">
            <div>
              <Label className="text-sm font-medium mb-3 block">Staged Rollout Percentage</Label>
              <div className="flex items-center gap-4">
                <Slider
                  value={rolloutPercent}
                  onValueChange={setRolloutPercent}
                  min={1}
                  max={100}
                  step={1}
                  className="flex-1"
                />
                <span className="text-sm font-medium w-12 text-right">{rolloutPercent[0]}%</span>
              </div>
              <div className="flex gap-2 mt-3 flex-wrap">
                {rolloutOptions.map((percent) => (
                  <Button
                    key={percent}
                    size="sm"
                    variant={rolloutPercent[0] === percent ? "default" : "outline"}
                    onClick={() => setRolloutPercent([percent])}
                  >
                    {percent}%
                  </Button>
                ))}
              </div>
            </div>

            <div className="flex items-center space-x-2">
              <Checkbox
                id="wifi-only"
                checked={wifiOnly}
                onCheckedChange={(checked) => setWifiOnly(checked as boolean)}
              />
              <Label
                htmlFor="wifi-only"
                className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
              >
                WiFi only (download only when connected to WiFi)
              </Label>
            </div>

            <div className="flex items-center space-x-2">
              <Checkbox
                id="must-install"
                checked={mustInstall}
                onCheckedChange={(checked) => setMustInstall(checked as boolean)}
              />
              <Label
                htmlFor="must-install"
                className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
              >
                Must install (force update on all devices)
              </Label>
            </div>
          </div>

          <div className="rounded-lg bg-muted p-4 text-sm">
            <p className="font-medium mb-2">What happens next?</p>
            <ul className="space-y-1 text-muted-foreground">
              <li>• This APK will become the current version for OTA updates</li>
              <li>• {rolloutPercent[0]}% of eligible devices will receive the update</li>
              {wifiOnly && <li>• Updates will only download over WiFi connections</li>}
              {mustInstall && <li>• All devices will be forced to install this update</li>}
            </ul>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button onClick={handlePromote} disabled={isSubmitting}>
            {isSubmitting ? 'Promoting...' : 'Promote'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// RolloutDialog Component
function RolloutDialog({
  isOpen,
  onClose,
  apk,
  onRolloutComplete,
}: {
  isOpen: boolean
  onClose: () => void
  apk: ApkVersion
  onRolloutComplete: () => void
}) {
  const [newRolloutPercent, setNewRolloutPercent] = useState([apk.staged_rollout_percent || 100])
  const [isSubmitting, setIsSubmitting] = useState(false)

  const rolloutOptions = [1, 5, 10, 25, 50, 100]

  const handleAdjustRollout = async () => {
    setIsSubmitting(true)
    try {
      const token = localStorage.getItem('access_token')
      const response = await fetch(`/v1/apk/${apk.id}/rollout`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          staged_rollout_percent: newRolloutPercent[0],
        }),
      })

      if (response.ok) {
        toast.success(`Adjusted rollout to ${newRolloutPercent[0]}%`)
        onRolloutComplete()
      } else {
        const error = await response.json()
        toast.error(error.error || error.detail || 'Failed to adjust rollout')
      }
    } catch (error) {
      console.error('Failed to adjust rollout:', error)
      toast.error('Failed to adjust rollout')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Adjust Rollout Percentage</DialogTitle>
          <DialogDescription>
            Modify the staged rollout percentage for {apk.package_name} v{apk.version_name}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div className="rounded-lg bg-muted p-3">
                <div className="text-muted-foreground mb-1">Current Rollout</div>
                <div className="text-2xl font-semibold">{apk.staged_rollout_percent || 100}%</div>
              </div>
              <div className="rounded-lg bg-muted p-3">
                <div className="text-muted-foreground mb-1">New Rollout</div>
                <div className="text-2xl font-semibold text-primary">{newRolloutPercent[0]}%</div>
              </div>
            </div>

            <div>
              <Label className="text-sm font-medium mb-3 block">New Rollout Percentage</Label>
              <div className="flex items-center gap-4">
                <Slider
                  value={newRolloutPercent}
                  onValueChange={setNewRolloutPercent}
                  min={1}
                  max={100}
                  step={1}
                  className="flex-1"
                />
                <span className="text-sm font-medium w-12 text-right">{newRolloutPercent[0]}%</span>
              </div>
              <div className="flex gap-2 mt-3 flex-wrap">
                {rolloutOptions.map((percent) => (
                  <Button
                    key={percent}
                    size="sm"
                    variant={newRolloutPercent[0] === percent ? "default" : "outline"}
                    onClick={() => setNewRolloutPercent([percent])}
                  >
                    {percent}%
                  </Button>
                ))}
              </div>
            </div>

            {apk.deployment_stats && (
              <div className="rounded-lg bg-muted p-4 text-sm">
                <p className="font-medium mb-2">Current Adoption Stats</p>
                <div className="grid grid-cols-2 gap-2 text-muted-foreground">
                  {apk.deployment_stats.adoption_rate !== undefined && (
                    <div>Adoption Rate: {apk.deployment_stats.adoption_rate.toFixed(1)}%</div>
                  )}
                  {apk.deployment_stats.total_checks !== undefined && (
                    <div>Total Checks: {apk.deployment_stats.total_checks}</div>
                  )}
                  {apk.deployment_stats.installs_success !== undefined && (
                    <div>Successful Installs: {apk.deployment_stats.installs_success}</div>
                  )}
                  {apk.deployment_stats.installs_failed !== undefined && (
                    <div>Failed Installs: {apk.deployment_stats.installs_failed}</div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button onClick={handleAdjustRollout} disabled={isSubmitting}>
            {isSubmitting ? 'Adjusting...' : 'Adjust Rollout'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// RollbackDialog Component
function RollbackDialog({
  isOpen,
  onClose,
  currentApk,
  apkVersions,
  onRollbackComplete,
}: {
  isOpen: boolean
  onClose: () => void
  currentApk: ApkVersion
  apkVersions: ApkVersion[]
  onRollbackComplete: () => void
}) {
  const [forceDowngrade, setForceDowngrade] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)

  // Find the previous version (highest version code that's lower than current)
  const previousApk = apkVersions
    .filter(apk => !apk.is_current && apk.version_code < currentApk.version_code)
    .sort((a, b) => b.version_code - a.version_code)[0]

  const handleRollback = async () => {
    setIsSubmitting(true)
    try {
      const token = localStorage.getItem('access_token')
      const response = await fetch('/v1/apk/rollback', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          force_downgrade: forceDowngrade,
        }),
      })

      if (response.ok) {
        toast.success('Rollback initiated successfully')
        onRollbackComplete()
      } else {
        const error = await response.json()
        toast.error(error.error || error.detail || 'Failed to rollback')
      }
    } catch (error) {
      console.error('Failed to rollback:', error)
      toast.error('Failed to rollback')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Rollback OTA Update</DialogTitle>
          <DialogDescription>
            Rollback to the previous version and stop distributing the current update
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="rounded-lg border border-orange-200 dark:border-orange-800 bg-orange-50 dark:bg-orange-950/20 p-4">
              <div className="text-xs text-muted-foreground mb-2">Current Version</div>
              <div className="font-semibold">{currentApk.version_name}</div>
              <div className="text-sm text-muted-foreground">Code: {currentApk.version_code}</div>
              {currentApk.staged_rollout_percent && (
                <div className="text-xs text-orange-600 dark:text-orange-400 mt-1">
                  Rollout: {currentApk.staged_rollout_percent}%
                </div>
              )}
            </div>

            <div className="rounded-lg border border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-950/20 p-4">
              <div className="text-xs text-muted-foreground mb-2">Rolling Back To</div>
              {previousApk ? (
                <>
                  <div className="font-semibold">{previousApk.version_name}</div>
                  <div className="text-sm text-muted-foreground">Code: {previousApk.version_code}</div>
                </>
              ) : (
                <div className="text-sm text-muted-foreground">No previous version available</div>
              )}
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <Checkbox
              id="force-downgrade"
              checked={forceDowngrade}
              onCheckedChange={(checked) => setForceDowngrade(checked as boolean)}
            />
            <Label
              htmlFor="force-downgrade"
              className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
            >
              Force downgrade on all devices
            </Label>
          </div>

          <div className="rounded-lg bg-orange-50 dark:bg-orange-950/20 border border-orange-200 dark:border-orange-800 p-4 text-sm">
            <p className="font-medium text-orange-900 dark:text-orange-100 mb-2">⚠️ Warning</p>
            <ul className="space-y-1 text-orange-800 dark:text-orange-200">
              <li>• This will stop distributing the current version</li>
              {previousApk && <li>• Devices will be offered version {previousApk.version_name} instead</li>}
              {forceDowngrade && <li>• All devices will be forced to downgrade</li>}
              {!previousApk && <li>• No previous version exists - rollback will disable OTA updates</li>}
            </ul>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button 
            onClick={handleRollback} 
            disabled={isSubmitting}
            className="bg-orange-600 hover:bg-orange-700 text-white"
          >
            {isSubmitting ? 'Rolling Back...' : 'Confirm Rollback'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
