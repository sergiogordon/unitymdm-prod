"use client"

import { useState, useEffect } from "react"
import { Header } from "@/components/header"
import { PageHeader } from "@/components/page-header"
import { SettingsDrawer } from "@/components/settings-drawer"
import { Package, Upload, Download, Trash2, RefreshCw, Send, X, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { format } from "date-fns"
import { toZonedTime } from "date-fns-tz"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

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
  const [showUploadModal, setShowUploadModal] = useState(false)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploadVersionName, setUploadVersionName] = useState("")
  const [uploadPackageName, setUploadPackageName] = useState("")
  const [uploadBuildType, setUploadBuildType] = useState<"debug" | "release">("release")
  const [isUploading, setIsUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)

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

  const handleRefresh = () => {
    fetchApkBuilds()
  }

  const handleDownload = async (buildId: number, filename: string) => {
    try {
      console.log(`[APK DOWNLOAD] Starting download for build ID: ${buildId}, filename: ${filename}`)
      
      const response = await fetch(`/admin/apk/download/${buildId}`)
      
      console.log(`[APK DOWNLOAD] Response status: ${response.status}`)
      
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
      console.log(`[APK DOWNLOAD] Received blob of size: ${blob.size} bytes`)
      
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
      
      console.log(`[APK DOWNLOAD] Download initiated successfully`)
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
      
      fetchApkBuilds()
    } catch (err) {
      console.error('Delete error:', err)
      alert('Failed to delete APK build')
    }
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      if (!file.name.endsWith('.apk')) {
        alert('Please select a valid APK file')
        return
      }
      setUploadFile(file)
      // Try to extract version from filename (e.g., "app-1.2.3.apk")
      const versionMatch = file.name.match(/(\d+\.\d+\.\d+)/)
      if (versionMatch) {
        setUploadVersionName(versionMatch[1])
      }
    }
  }

  const handleUploadApk = async () => {
    if (!uploadFile || !uploadVersionName || !uploadPackageName) {
      alert('Please provide file, version name, and package name')
      return
    }

    setIsUploading(true)
    setUploadProgress(0)
    setError(null)

    try {
      // Generate build ID and version code
      const buildId = `manual-${Date.now()}`
      const versionCode = parseInt(uploadVersionName.replace(/\./g, '')) || Math.floor(Date.now() / 1000)

      // Step 1: Register the APK build
      const registerResponse = await fetch('/api/proxy/admin/apk/register', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          build_id: buildId,
          version_code: versionCode,
          version_name: uploadVersionName,
          build_type: uploadBuildType,
          file_size_bytes: uploadFile.size,
          package_name: uploadPackageName
        })
      })

      if (!registerResponse.ok) {
        const errorData = await registerResponse.json().catch(() => ({}))
        throw new Error(errorData.detail || 'Failed to register APK')
      }

      setUploadProgress(30)

      // Step 2: Upload the actual file
      const formData = new FormData()
      formData.append('file', uploadFile)
      formData.append('build_id', buildId)
      formData.append('version_code', versionCode.toString())
      formData.append('version_name', uploadVersionName)
      formData.append('build_type', uploadBuildType)
      formData.append('package_name', uploadPackageName)

      const uploadResponse = await fetch('/api/proxy/admin/apk/upload', {
        method: 'POST',
        body: formData
      })

      if (!uploadResponse.ok) {
        const errorData = await uploadResponse.json().catch(() => ({}))
        throw new Error(errorData.detail || 'Failed to upload APK file')
      }

      setUploadProgress(100)

      // Success!
      setTimeout(() => {
        setShowUploadModal(false)
        setUploadFile(null)
        setUploadVersionName("")
        setUploadPackageName("")
        setUploadBuildType("release")
        fetchApkBuilds()
      }, 500)

    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed')
      console.error('Upload error:', err)
    } finally {
      setIsUploading(false)
    }
  }

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
                              onClick={() => window.location.href = `/apk-deploy/${apk.build_id}`}
                              title="Deploy to Devices"
                              className="text-blue-600 hover:text-blue-700 hover:bg-blue-50 dark:text-blue-400 dark:hover:text-blue-300 dark:hover:bg-blue-950"
                            >
                              <Send className="h-4 w-4" />
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

      {/* Upload Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <Card className="w-full max-w-md rounded-2xl border border-border bg-card p-6 shadow-xl">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-xl font-semibold text-card-foreground">Upload APK</h2>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setShowUploadModal(false)
                  setUploadFile(null)
                  setUploadVersionName("")
                  setUploadPackageName("")
                  setError(null)
                }}
                disabled={isUploading}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>

            {error && (
              <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800 dark:border-red-800 dark:bg-red-900/20 dark:text-red-200">
                {error}
              </div>
            )}

            <div className="space-y-4">
              {/* File Input */}
              <div>
                <Label htmlFor="apk-file" className="mb-2 block text-sm font-medium">
                  APK File
                </Label>
                <Input
                  id="apk-file"
                  type="file"
                  accept=".apk"
                  onChange={handleFileSelect}
                  disabled={isUploading}
                  className="cursor-pointer"
                />
                {uploadFile && (
                  <p className="mt-1 text-sm text-muted-foreground">
                    Selected: {uploadFile.name} ({formatFileSize(uploadFile.size)})
                  </p>
                )}
              </div>

              {/* Package Name Input */}
              <div>
                <Label htmlFor="package-name" className="mb-2 block text-sm font-medium">
                  Package Name
                </Label>
                <Input
                  id="package-name"
                  type="text"
                  placeholder="e.g., org.zwanoo.android.speedtest"
                  value={uploadPackageName}
                  onChange={(e) => setUploadPackageName(e.target.value)}
                  disabled={isUploading}
                />
                <p className="mt-1 text-xs text-muted-foreground">
                  Android package name (e.g., com.example.app)
                </p>
              </div>

              {/* Version Name Input */}
              <div>
                <Label htmlFor="version-name" className="mb-2 block text-sm font-medium">
                  Version Name
                </Label>
                <Input
                  id="version-name"
                  type="text"
                  placeholder="e.g., 1.0.0"
                  value={uploadVersionName}
                  onChange={(e) => setUploadVersionName(e.target.value)}
                  disabled={isUploading}
                />
                <p className="mt-1 text-xs text-muted-foreground">
                  Human-readable version (e.g., 1.2.3)
                </p>
              </div>

              {/* Build Type Selector */}
              <div>
                <Label className="mb-2 block text-sm font-medium">Build Type</Label>
                <div className="flex gap-2">
                  <Button
                    variant={uploadBuildType === "debug" ? "default" : "outline"}
                    size="sm"
                    onClick={() => setUploadBuildType("debug")}
                    disabled={isUploading}
                    className="flex-1"
                  >
                    Debug
                  </Button>
                  <Button
                    variant={uploadBuildType === "release" ? "default" : "outline"}
                    size="sm"
                    onClick={() => setUploadBuildType("release")}
                    disabled={isUploading}
                    className="flex-1"
                  >
                    Release
                  </Button>
                </div>
              </div>

              {/* Progress Bar */}
              {isUploading && (
                <div>
                  <div className="mb-1 flex justify-between text-sm">
                    <span className="text-muted-foreground">Uploading...</span>
                    <span className="font-medium">{uploadProgress}%</span>
                  </div>
                  <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full bg-primary transition-all duration-300"
                      style={{ width: `${uploadProgress}%` }}
                    />
                  </div>
                </div>
              )}

              {/* Upload Button */}
              <div className="flex gap-2 pt-2">
                <Button
                  variant="outline"
                  onClick={() => {
                    setShowUploadModal(false)
                    setUploadFile(null)
                    setUploadVersionName("")
                    setUploadPackageName("")
                    setError(null)
                  }}
                  disabled={isUploading}
                  className="flex-1"
                >
                  Cancel
                </Button>
                <Button
                  onClick={handleUploadApk}
                  disabled={!uploadFile || !uploadVersionName || !uploadPackageName || isUploading}
                  className="flex-1 gap-2"
                >
                  {isUploading ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Uploading...
                    </>
                  ) : (
                    <>
                      <Upload className="h-4 w-4" />
                      Upload
                    </>
                  )}
                </Button>
              </div>
            </div>
          </Card>
        </div>
      )}

      <SettingsDrawer isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} />
    </div>
  )
}
