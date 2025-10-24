"use client"

import { useState, useEffect } from "react"
import { Upload, Package, Download, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Header } from "@/components/header"
import { Sidebar } from "@/components/sidebar"
import { SettingsDrawer } from "@/components/settings-drawer"
import { DemoApiService } from "@/lib/demoApiService"
import { formatAbsoluteTimestampCST } from "@/lib/utils"
import { toast } from "sonner"
import { useTheme } from "@/contexts/ThemeContext"

interface ApkVersion {
  id: number
  package_name: string
  version_name: string
  version_code: number
  file_size: number
  uploaded_at: string
  uploaded_by: string
}

export default function DemoApkManagementPage() {
  const { isDark, toggleTheme } = useTheme()
  const [isSidebarOpen, setIsSidebarOpen] = useState(true)
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  const [apkVersions, setApkVersions] = useState<ApkVersion[]>([])
  const [lastUpdated, setLastUpdated] = useState(Date.now())

  useEffect(() => {
    loadApkVersions()
  }, [])

  const loadApkVersions = async () => {
    try {
      const response = await DemoApiService.fetch('/v1/apk/versions')
      const data = await response.json()
      setApkVersions(data.versions || [])
      setLastUpdated(Date.now())
    } catch (error) {
      console.error('Failed to load APK versions:', error)
    }
  }

  const handleToggleSidebar = () => {
    setIsSidebarOpen(!isSidebarOpen)
  }

  const handleUpload = () => {
    toast.info('Upload disabled in demo mode')
  }

  const handleDeploy = (apk: ApkVersion) => {
    toast.success(`Deploy initiated for ${apk.package_name} v${apk.version_name} (demo mode)`)
  }

  const handleDelete = () => {
    toast.info('Delete disabled in demo mode')
  }

  const handleDownload = (apk: ApkVersion) => {
    toast.info(`Download disabled in demo mode. In production, this would download ${apk.package_name} v${apk.version_name}`)
  }

  return (
    <div className="min-h-screen">
      <Sidebar isOpen={isSidebarOpen} onToggle={handleToggleSidebar} />
      
      <Header
        lastUpdated={lastUpdated}
        alertCount={0}
        isDark={isDark}
        onToggleDark={toggleTheme}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onRefresh={loadApkVersions}
        onToggleSidebar={handleToggleSidebar}
      />

      <main className={`transition-all duration-300 px-6 pb-12 pt-20 md:px-8 ${isSidebarOpen ? 'lg:ml-64' : 'lg:ml-16'}`}>
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">APK Management</h2>
            <p className="mt-1 text-sm text-muted-foreground">Upload and deploy APK files to your fleet</p>
          </div>
          <Button onClick={handleUpload} className="gap-2">
            <Upload className="h-4 w-4" />
            Upload APK
          </Button>
        </div>

        {apkVersions.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <Package className="h-16 w-16 text-muted-foreground mb-4" />
            <h3 className="text-lg font-medium mb-2">No APK Versions</h3>
            <p className="text-sm text-muted-foreground mb-6">Upload your first APK to get started</p>
            <Button onClick={handleUpload} className="gap-2">
              <Upload className="h-4 w-4" />
              Upload APK
            </Button>
          </div>
        ) : (
          <div className="rounded-lg border border-border/40 bg-card">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border/40">
                    <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Package</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Version</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Size</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Uploaded</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Uploaded By</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {apkVersions.map((apk) => (
                    <tr key={apk.id} className="border-b border-border/40 last:border-0">
                      <td className="px-6 py-4">
                        <div className="font-medium">{apk.package_name}</div>
                      </td>
                      <td className="px-6 py-4">
                        <div className="text-sm">{apk.version_name}</div>
                        <div className="text-xs text-muted-foreground">Build {apk.version_code}</div>
                      </td>
                      <td className="px-6 py-4 text-sm">
                        {(apk.file_size / 1024 / 1024).toFixed(2)} MB
                      </td>
                      <td className="px-6 py-4 text-sm">
                        {formatAbsoluteTimestampCST(apk.uploaded_at)}
                      </td>
                      <td className="px-6 py-4 text-sm">
                        {apk.uploaded_by}
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2">
                          <Button size="sm" variant="outline" onClick={() => handleDownload(apk)}>
                            <Download className="h-4 w-4" />
                          </Button>
                          <Button size="sm" onClick={() => handleDeploy(apk)}>
                            Deploy
                          </Button>
                          <Button size="sm" variant="destructive" onClick={handleDelete}>
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </main>

      <SettingsDrawer 
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
      />
    </div>
  )
}
