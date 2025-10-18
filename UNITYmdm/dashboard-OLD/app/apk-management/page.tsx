"use client"

import { useState, useEffect } from "react"
import { Upload, Package, Trash2, Send, Download } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Header } from "@/components/header"
import { Sidebar } from "@/components/sidebar"
import { ProtectedLayout } from "@/components/protected-layout"
import { ApkUploadDialog } from "@/components/apk-upload-dialog"
import { ApkDeployDialog } from "@/components/apk-deploy-dialog"
import { toast } from "sonner"
import { formatAbsoluteTimestampCST } from "@/lib/utils"
import { SettingsDrawer } from "@/components/settings-drawer"
import { isDemoMode } from "@/lib/demoUtils"

interface ApkVersion {
  id: number
  package_name: string
  version_name: string
  version_code: number
  file_size: number
  uploaded_at: string
  uploaded_by: string
  deployment_stats?: {
    total_deployments: number
    last_deployed_at: string | null
    deployed_devices: number
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
                  deployed_devices: deviceIds.size
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
                    Last Deployed
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
                          <div className="font-medium">{apk.package_name}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="text-sm">
                        <div>{apk.version_name}</div>
                        <div className="text-muted-foreground">Code: {apk.version_code}</div>
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
                              <div className="text-muted-foreground">
                                {formatAbsoluteTimestampCST(apk.deployment_stats.last_deployed_at)}
                              </div>
                              <div className="text-xs text-muted-foreground">
                                {apk.deployment_stats.deployed_devices} device{apk.deployment_stats.deployed_devices !== 1 ? 's' : ''} · {apk.deployment_stats.total_deployments} deployment{apk.deployment_stats.total_deployments !== 1 ? 's' : ''}
                              </div>
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

      <SettingsDrawer
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
      />
    </div>
  )
}
