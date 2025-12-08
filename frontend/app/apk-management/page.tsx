"use client"

import { useState, useEffect } from "react"
import { Header } from "@/components/header"
import { PageHeader } from "@/components/page-header"
import { SettingsDrawer } from "@/components/settings-drawer"
import { ApkUploadDialog } from "@/components/apk-upload-dialog"
import { Package, Upload, Download, Trash2, RefreshCw, Send, AlertTriangle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { format } from "date-fns"
import { toZonedTime } from "date-fns-tz"
import { useTheme } from "@/contexts/ThemeContext"
import { clearApkBuildCache } from "@/lib/apk-build-cache"

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
  const { isDark, toggleTheme } = useTheme()
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  const [apkBuilds, setApkBuilds] = useState<ApkBuild[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showUploadModal, setShowUploadModal] = useState(false)
  const [selectedBuildIds, setSelectedBuildIds] = useState<Set<number>>(new Set())
  const [showBatchDeleteDialog, setShowBatchDeleteDialog] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)

  const fetchApkBuilds = async () => {
    setIsLoading(true)
    setError(null)
    try {
      const response = await fetch('/admin/apk/builds?build_type=release&limit=50')
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

  // Clean up selected IDs that no longer exist in the list
  useEffect(() => {
    if (apkBuilds.length > 0 && selectedBuildIds.size > 0) {
      const existingIds = new Set(apkBuilds.map(apk => apk.build_id))
      setSelectedBuildIds(prev => {
        const next = new Set<number>()
        prev.forEach(id => {
          if (existingIds.has(id)) {
            next.add(id)
          }
        })
        return next
      })
    }
  }, [apkBuilds])

  const handleRefresh = () => {
    fetchApkBuilds()
  }

  const handleDownload = async (buildId: number, filename: string) => {
    try {
      const response = await fetch(`/admin/apk/download/${buildId}`)
      
      if (!response.ok) {
        let errorMessage = 'Download failed'
        try {
          const errorData = await response.json()
          errorMessage = errorData.detail || errorData.error || errorMessage
          console.error(`[APK DOWNLOAD] Server error:`, errorData)
        } catch (parseErr) {
          console.error(`[APK DOWNLOAD] Failed to parse error response`, parseErr)
        }
        throw new Error(errorMessage)
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
      const errorMessage = err instanceof Error ? err.message : 'Failed to download APK'
      console.error('[APK DOWNLOAD] Download error:', err)
      alert(`Failed to download APK: ${errorMessage}`)
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
      
      // Clear cache when APK is deleted
      clearApkBuildCache()
      fetchApkBuilds()
      setSelectedBuildIds(prev => {
        const next = new Set(prev)
        next.delete(buildId)
        return next
      })
    } catch (err) {
      console.error('Delete error:', err)
      alert('Failed to delete APK build')
    }
  }

  const handleToggleSelect = (buildId: number) => {
    setSelectedBuildIds(prev => {
      const next = new Set(prev)
      if (next.has(buildId)) {
        next.delete(buildId)
      } else {
        next.add(buildId)
      }
      return next
    })
  }

  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      setSelectedBuildIds(new Set(apkBuilds.map(apk => apk.build_id)))
    } else {
      setSelectedBuildIds(new Set())
    }
  }

  const handleBatchDelete = async () => {
    if (selectedBuildIds.size === 0) return

    setIsDeleting(true)
    setError(null)

    const buildIdsArray = Array.from(selectedBuildIds)
    const failedDeletes: { buildId: number; filename: string }[] = []
    const successfulDeletes: number[] = []

    // Delete APKs sequentially to avoid overwhelming the server
    for (const buildId of buildIdsArray) {
      const apk = apkBuilds.find(a => a.build_id === buildId)
      if (!apk) continue

      try {
        const response = await fetch(`/admin/apk/builds?build_id=${buildId}`, {
          method: 'DELETE',
        })
        
        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}))
          throw new Error(errorData.detail || errorData.error || 'Delete failed')
        }

        successfulDeletes.push(buildId)
      } catch (err) {
        console.error(`Failed to delete APK ${buildId}:`, err)
        failedDeletes.push({ buildId, filename: apk.filename })
      }
    }

    setIsDeleting(false)
    setShowBatchDeleteDialog(false)

    // Update UI optimistically - remove successfully deleted items
    if (successfulDeletes.length > 0) {
      // Clear cache when APKs are deleted
      clearApkBuildCache()
      setApkBuilds(prev => prev.filter(apk => !successfulDeletes.includes(apk.build_id)))
      setSelectedBuildIds(prev => {
        const next = new Set(prev)
        successfulDeletes.forEach(id => next.delete(id))
        return next
      })
    }

    // Show results
    if (failedDeletes.length > 0) {
      const failedNames = failedDeletes.map(f => f.filename).join(', ')
      const message = successfulDeletes.length > 0
        ? `Successfully deleted ${successfulDeletes.length} APK(s). Failed to delete: ${failedNames}`
        : `Failed to delete APK(s): ${failedNames}`
      setError(message)
    } else if (successfulDeletes.length > 0) {
      // Refresh to ensure consistency
      fetchApkBuilds()
    }
  }

  const getSelectedApks = () => {
    return apkBuilds.filter(apk => selectedBuildIds.has(apk.build_id))
  }

  const isAllSelected = apkBuilds.length > 0 && selectedBuildIds.size === apkBuilds.length


  const formatFileSize = (bytes: number): string => {
    const mb = bytes / (1024 * 1024)
    return `${mb.toFixed(1)} MB`
  }

  const formatUploadedTime = (isoString: string): string => {
    const date = new Date(isoString)
    const cstDate = toZonedTime(date, 'America/Chicago')
    return format(cstDate, "MMM d, yyyy 'at' h:mm a 'CST'")
  }

  return (
    <div className="min-h-screen">
      <Header />

      <main className="mx-auto max-w-[1280px] px-6 pb-12 pt-[84px] md:px-8">
        <PageHeader
          icon={<Package className="h-8 w-8" />}
          title="APK Management"
          description="Upload, manage, and deploy Android application packages to your device fleet."
        />

        <div className="space-y-6">
          <Card className="rounded-2xl border border-border bg-card p-6 shadow-sm">
            <div className="mb-6 flex items-center justify-between">
              <div className="flex items-center gap-4">
                <h2 className="text-lg font-semibold text-card-foreground">Available APK Files</h2>
                {selectedBuildIds.size > 0 && (
                  <span className="text-sm text-muted-foreground">
                    {selectedBuildIds.size} selected
                  </span>
                )}
              </div>
              <div className="flex gap-2">
                {selectedBuildIds.size > 0 && (
                  <Button
                    onClick={() => setShowBatchDeleteDialog(true)}
                    variant="destructive"
                    className="gap-2"
                    disabled={isDeleting || isLoading}
                  >
                    <Trash2 className="h-4 w-4" />
                    Delete Selected ({selectedBuildIds.size})
                  </Button>
                )}
                <Button onClick={handleRefresh} variant="outline" className="gap-2" disabled={isLoading}>
                  <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
                  Refresh
                </Button>
                <Button onClick={() => setShowUploadModal(true)} className="gap-2">
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
                Loading release builds...
              </div>
            ) : apkBuilds.length === 0 ? (
              <div className="py-12 text-center text-muted-foreground">
                No release builds found. Production builds from CI will appear here automatically.
              </div>
            ) : (
              <div className="overflow-hidden rounded-lg border border-border">
                <table className="w-full">
                  <thead className="border-b border-border bg-muted/50">
                    <tr>
                      <th className="w-12 px-4 py-3">
                        <Checkbox
                          checked={isAllSelected}
                          onCheckedChange={handleSelectAll}
                          aria-label="Select all APKs"
                        />
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground">File Name</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground">Version</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground">Size</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground">Uploaded</th>
                      <th className="px-4 py-3 text-right text-xs font-semibold text-muted-foreground">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {apkBuilds.map((apk) => {
                      const isSelected = selectedBuildIds.has(apk.build_id)
                      return (
                        <tr
                          key={apk.build_id}
                          className={`border-b border-border last:border-0 transition-colors ${
                            isSelected ? 'bg-primary/5' : ''
                          }`}
                        >
                          <td className="px-4 py-3">
                            <Checkbox
                              checked={isSelected}
                              onCheckedChange={() => handleToggleSelect(apk.build_id)}
                              onClick={(e) => e.stopPropagation()}
                              aria-label={`Select ${apk.filename}`}
                            />
                          </td>
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
                                disabled={isDeleting}
                              >
                                <Download className="h-4 w-4" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => window.location.href = `/apk-deploy/${apk.build_id}`}
                                title="Deploy to Devices"
                                className="text-blue-600 hover:text-blue-700 hover:bg-blue-50 dark:text-blue-400 dark:hover:text-blue-300 dark:hover:bg-blue-950"
                                disabled={isDeleting}
                              >
                                <Send className="h-4 w-4" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleDelete(apk.build_id, apk.filename)}
                                title="Delete APK"
                                disabled={isDeleting}
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      </main>

      <ApkUploadDialog 
        isOpen={showUploadModal}
        onClose={() => setShowUploadModal(false)}
        onUploadComplete={() => {
          // Clear cache when APK is uploaded
          clearApkBuildCache()
          fetchApkBuilds()
        }}
      />

      <SettingsDrawer isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} />

      {/* Batch Delete Confirmation Dialog */}
      <Dialog open={showBatchDeleteDialog} onOpenChange={setShowBatchDeleteDialog}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-destructive">
              <AlertTriangle className="h-5 w-5" />
              Delete {selectedBuildIds.size} APK{selectedBuildIds.size !== 1 ? 's' : ''}
            </DialogTitle>
            <DialogDescription className="text-left pt-2">
              This action <strong>cannot be undone</strong>. This will permanently delete the selected APK files.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            {getSelectedApks().length > 0 && (
              <div>
                <div className="text-sm font-medium mb-2">APKs to be deleted:</div>
                <div className="mt-2 rounded-md border border-border bg-muted/50 p-3 max-h-[200px] overflow-y-auto">
                  <ul className="text-sm space-y-1">
                    {getSelectedApks().slice(0, 10).map((apk) => (
                      <li key={apk.build_id} className="text-muted-foreground font-mono text-xs">
                        • {apk.filename} ({apk.version_name})
                      </li>
                    ))}
                    {getSelectedApks().length > 10 && (
                      <li className="text-muted-foreground italic">
                        ... and {getSelectedApks().length - 10} more
                      </li>
                    )}
                  </ul>
                </div>
              </div>
            )}
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowBatchDeleteDialog(false)}
              disabled={isDeleting}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleBatchDelete}
              disabled={isDeleting}
            >
              {isDeleting ? "Deleting..." : `Delete ${selectedBuildIds.size} APK${selectedBuildIds.size !== 1 ? 's' : ''}`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
