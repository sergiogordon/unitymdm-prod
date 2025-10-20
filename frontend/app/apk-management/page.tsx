"use client"

import { useState, useEffect } from "react"
import { Header } from "@/components/header"
import { PageHeader } from "@/components/page-header"
import { SettingsDrawer } from "@/components/settings-drawer"
import { Package, Upload, Download, Trash2, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"

interface ApkBuild {
  build_id: number
  filename: string
  version_name: string
  version_code: number
  file_size_bytes: number
  uploaded_at: string
  uploaded_by: string
  build_type: string
  ci_run_id?: string
  git_sha?: string
}

export default function ApkManagementPage() {
  const [isDark, setIsDark] = useState(false)
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  const [apkBuilds, setApkBuilds] = useState<ApkBuild[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add("dark")
    } else {
      document.documentElement.classList.remove("dark")
    }
  }, [isDark])

  const fetchApkBuilds = async () => {
    setIsLoading(true)
    setError(null)
    try {
      const response = await fetch('/admin/apk/builds?build_type=debug&limit=50')
      if (!response.ok) {
        throw new Error('Failed to fetch APK builds')
      }
      const data = await response.json()
      setApkBuilds(data.builds || [])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load APK builds')
      console.error('Error fetching APK builds:', err)
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchApkBuilds()
  }, [])

  const handleRefresh = () => {
    fetchApkBuilds()
  }

  const handleDownload = async (buildId: number, filename: string) => {
    try {
      const response = await fetch(`/admin/apk/download/${buildId}`)
      if (!response.ok) {
        throw new Error('Download failed')
      }
      
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (err) {
      console.error('Download error:', err)
      alert('Failed to download APK')
    }
  }

  const handleDelete = async (buildId: number, filename: string) => {
    if (!confirm(`Are you sure you want to delete ${filename}?`)) {
      return
    }

    try {
      const response = await fetch(`/admin/apk/builds?build_id=${buildId}`, {
        method: 'DELETE',
      })
      if (!response.ok) {
        throw new Error('Delete failed')
      }
      
      fetchApkBuilds()
    } catch (err) {
      console.error('Delete error:', err)
      alert('Failed to delete APK build')
    }
  }

  const formatFileSize = (bytes: number): string => {
    const mb = bytes / (1024 * 1024)
    return `${mb.toFixed(1)} MB`
  }

  const formatUploadedTime = (isoString: string): string => {
    const date = new Date(isoString)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMins / 60)
    const diffDays = Math.floor(diffHours / 24)

    if (diffMins < 60) return `${diffMins} minute${diffMins !== 1 ? 's' : ''} ago`
    if (diffHours < 24) return `${diffHours} hour${diffHours !== 1 ? 's' : ''} ago`
    if (diffDays < 7) return `${diffDays} day${diffDays !== 1 ? 's' : ''} ago`
    return date.toLocaleDateString()
  }

  return (
    <div className="min-h-screen">
      <Header
        isDark={isDark}
        onToggleDark={() => setIsDark(!isDark)}
      />

      <main className="mx-auto max-w-[1280px] px-6 pb-12 pt-[84px] md:px-8">
        <PageHeader
          icon={<Package className="h-8 w-8" />}
          title="APK Management"
          description="Upload, manage, and deploy Android application packages to your device fleet."
        />

        <div className="space-y-6">
          <Card className="rounded-2xl border border-border bg-card p-6 shadow-sm">
            <div className="mb-6 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-card-foreground">Available APK Files</h2>
              <div className="flex gap-2">
                <Button onClick={handleRefresh} variant="outline" className="gap-2" disabled={isLoading}>
                  <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
                  Refresh
                </Button>
                <Button className="gap-2">
                  <Upload className="h-4 w-4" />
                  Upload APK
                </Button>
              </div>
            </div>

            {error && (
              <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-800 dark:bg-red-900/20 dark:text-red-200">
                {error}
              </div>
            )}

            {isLoading ? (
              <div className="py-12 text-center text-muted-foreground">
                Loading APK builds...
              </div>
            ) : apkBuilds.length === 0 ? (
              <div className="py-12 text-center text-muted-foreground">
                No APK builds found. Builds from CI will appear here automatically.
              </div>
            ) : (
              <div className="overflow-hidden rounded-lg border border-border">
                <table className="w-full">
                  <thead className="border-b border-border bg-muted/50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground">File Name</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground">Version</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground">Size</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground">Uploaded</th>
                      <th className="px-4 py-3 text-right text-xs font-semibold text-muted-foreground">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {apkBuilds.map((apk) => (
                      <tr key={apk.build_id} className="border-b border-border last:border-0">
                        <td className="px-4 py-3 font-mono text-sm text-card-foreground">{apk.filename}</td>
                        <td className="px-4 py-3 text-sm text-muted-foreground">{apk.version_name}</td>
                        <td className="px-4 py-3 text-sm text-muted-foreground">
                          {formatFileSize(apk.file_size_bytes)}
                        </td>
                        <td className="px-4 py-3 text-sm text-muted-foreground">
                          {formatUploadedTime(apk.uploaded_at)}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <div className="flex items-center justify-end gap-2">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleDownload(apk.build_id, apk.filename)}
                              title="Download APK"
                            >
                              <Download className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleDelete(apk.build_id, apk.filename)}
                              title="Delete APK"
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      </main>

      <SettingsDrawer isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} />
    </div>
  )
}
