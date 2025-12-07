"use client"

import { useState, useCallback } from "react"
import { Upload, X, FileIcon } from "lucide-react"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { toast } from "sonner"
import { Progress } from "@/components/ui/progress"

interface ApkUploadDialogProps {
  isOpen: boolean
  onClose: () => void
  onUploadComplete: () => void
}

const MAX_FILE_SIZE = 500 * 1024 * 1024 // 500 MB
const CHUNK_SIZE = 5 * 1024 * 1024 // 5 MB chunks

export function ApkUploadDialog({ isOpen, onClose, onUploadComplete }: ApkUploadDialogProps) {
  const [file, setFile] = useState<File | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [packageName, setPackageName] = useState("")
  const [versionName, setVersionName] = useState("")
  const [versionCode, setVersionCode] = useState("")
  const [isUploading, setIsUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    
    const droppedFile = e.dataTransfer.files[0]
    if (droppedFile && droppedFile.name.endsWith('.apk')) {
      if (droppedFile.size > MAX_FILE_SIZE) {
        toast.error('File size exceeds 500 MB limit')
        return
      }
      setFile(droppedFile)
    } else {
      toast.error('Please upload a valid APK file')
    }
  }, [])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }, [])

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0]
    if (selectedFile && selectedFile.name.endsWith('.apk')) {
      if (selectedFile.size > MAX_FILE_SIZE) {
        toast.error('File size exceeds 500 MB limit')
        return
      }
      setFile(selectedFile)
    } else {
      toast.error('Please upload a valid APK file')
    }
  }

  const uploadChunkWithRetry = async (
    chunk: Blob,
    uploadId: string,
    chunkIndex: number,
    totalChunks: number,
    retries = 3
  ): Promise<boolean> => {
    for (let attempt = 0; attempt < retries; attempt++) {
      try {
        console.log(`[UPLOAD] Uploading chunk ${chunkIndex + 1}/${totalChunks} (attempt ${attempt + 1}/${retries})`, {
          uploadId,
          chunkIndex,
          chunkSize: chunk.size,
          filename: file!.name
        })

        const formData = new FormData()
        formData.append('file', chunk)
        formData.append('upload_id', uploadId)
        formData.append('chunk_index', chunkIndex.toString())
        formData.append('total_chunks', totalChunks.toString())
        formData.append('filename', file!.name)

        const token = localStorage.getItem('auth_token')
        if (!token) {
          console.error('[UPLOAD] No auth token found')
          toast.error('Authentication required. Please sign in again.')
          return false
        }

        const response = await fetch('/v1/apk/upload-chunk', {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
          },
          body: formData,
        })

        if (response.ok) {
          const responseData = await response.json().catch(() => ({}))
          console.log(`[UPLOAD] Chunk ${chunkIndex + 1}/${totalChunks} uploaded successfully`, responseData)
          return true
        }

        const errorText = await response.text().catch(() => 'Unknown error')
        const errorData = (() => {
          try {
            return JSON.parse(errorText)
          } catch {
            return { error: errorText || `HTTP ${response.status}: ${response.statusText}` }
          }
        })()

        console.error(`[UPLOAD] Chunk ${chunkIndex + 1}/${totalChunks} upload failed (attempt ${attempt + 1}/${retries})`, {
          status: response.status,
          statusText: response.statusText,
          error: errorData
        })

        if (attempt < retries - 1) {
          const delay = 1000 * (attempt + 1)
          console.log(`[UPLOAD] Retrying chunk ${chunkIndex + 1} in ${delay}ms...`)
          await new Promise(resolve => setTimeout(resolve, delay))
        } else {
          const errorMessage = errorData.error || errorData.details || `HTTP ${response.status}: ${response.statusText}`
          toast.error(`Failed to upload chunk ${chunkIndex + 1}/${totalChunks}: ${errorMessage}`)
        }
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'Unknown error'
        console.error(`[UPLOAD] Chunk ${chunkIndex + 1}/${totalChunks} upload error (attempt ${attempt + 1}/${retries})`, {
          error: errorMessage,
          errorObject: error
        })

        if (attempt < retries - 1) {
          const delay = 1000 * (attempt + 1)
          console.log(`[UPLOAD] Retrying chunk ${chunkIndex + 1} in ${delay}ms after error...`)
          await new Promise(resolve => setTimeout(resolve, delay))
        } else {
          toast.error(`Failed to upload chunk ${chunkIndex + 1}/${totalChunks}: ${errorMessage}`)
        }
      }
    }
    return false
  }

  const handleUpload = async () => {
    if (!file || !packageName || !versionName || !versionCode) {
      toast.error('Please fill in all fields')
      return
    }

    setIsUploading(true)
    setUploadProgress(0)

    const uploadId = `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
    const totalChunks = Math.ceil(file.size / CHUNK_SIZE)

    console.log('[UPLOAD] Starting upload', {
      filename: file.name,
      fileSize: file.size,
      totalChunks,
      uploadId,
      packageName,
      versionName,
      versionCode
    })

    try {
      for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex++) {
        const start = chunkIndex * CHUNK_SIZE
        const end = Math.min(start + CHUNK_SIZE, file.size)
        const chunk = file.slice(start, end)

        const success = await uploadChunkWithRetry(chunk, uploadId, chunkIndex, totalChunks)
        
        if (!success) {
          console.error(`[UPLOAD] Upload failed at chunk ${chunkIndex + 1}/${totalChunks}`)
          setIsUploading(false)
          setUploadProgress(0)
          return
        }

        const progress = Math.round(((chunkIndex + 1) / totalChunks) * 100)
        setUploadProgress(progress)
        console.log(`[UPLOAD] Progress: ${progress}% (${chunkIndex + 1}/${totalChunks} chunks)`)
      }

      console.log('[UPLOAD] All chunks uploaded, finalizing...')
      const token = localStorage.getItem('auth_token')
      if (!token) {
        console.error('[UPLOAD] No auth token for finalization')
        toast.error('Authentication required. Please sign in again.')
        setIsUploading(false)
        setUploadProgress(0)
        return
      }

      const completeResponse = await fetch('/v1/apk/complete', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          upload_id: uploadId,
          package_name: packageName,
          version_name: versionName,
          version_code: parseInt(versionCode),
          filename: file.name,
          total_chunks: totalChunks,
          build_type: 'release',
        }),
      })

      if (completeResponse.ok) {
        const completeData = await completeResponse.json().catch(() => ({}))
        console.log('[UPLOAD] Upload completed successfully', completeData)
        toast.success('APK uploaded successfully')
        setIsUploading(false)
        setUploadProgress(0)
        onUploadComplete()
        handleClose()
      } else {
        const errorText = await completeResponse.text().catch(() => 'Unknown error')
        const errorData = (() => {
          try {
            return JSON.parse(errorText)
          } catch {
            return { error: errorText || `HTTP ${completeResponse.status}: ${completeResponse.statusText}` }
          }
        })()
        
        console.error('[UPLOAD] Finalization failed', {
          status: completeResponse.status,
          statusText: completeResponse.statusText,
          error: errorData
        })
        
        const errorMessage = errorData.error || errorData.details || `HTTP ${completeResponse.status}: ${completeResponse.statusText}`
        toast.error(`Failed to finalize upload: ${errorMessage}`)
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error'
      console.error('[UPLOAD] Upload error:', {
        error: errorMessage,
        errorObject: error
      })
      toast.error(`Failed to upload APK: ${errorMessage}`)
    } finally {
      setIsUploading(false)
      setUploadProgress(0)
    }
  }

  const handleClose = () => {
    if (isUploading) {
      return
    }
    setFile(null)
    setPackageName("")
    setVersionName("")
    setVersionCode("")
    setUploadProgress(0)
    onClose()
  }

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>Upload APK</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div
            className={`relative rounded-lg border-2 border-dashed p-8 text-center transition-colors ${
              isDragging 
                ? 'border-primary bg-primary/5' 
                : file 
                ? 'border-border bg-muted/50' 
                : 'border-border hover:border-muted-foreground/50'
            }`}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
          >
            {file ? (
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <FileIcon className="h-8 w-8 text-primary" />
                  <div className="text-left">
                    <p className="font-medium">{file.name}</p>
                    <p className="text-sm text-muted-foreground">{formatFileSize(file.size)}</p>
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setFile(null)}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            ) : (
              <>
                <Upload className="mx-auto h-10 w-10 text-muted-foreground" />
                <p className="mt-2 text-sm font-medium">Drop APK file here</p>
                <p className="mt-1 text-xs text-muted-foreground">or click to browse</p>
                <input
                  type="file"
                  accept=".apk"
                  onChange={handleFileSelect}
                  className="absolute inset-0 cursor-pointer opacity-0"
                />
              </>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="package-name">Package Name</Label>
            <Input
              id="package-name"
              placeholder="com.example.app"
              value={packageName}
              onChange={(e) => setPackageName(e.target.value)}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="version-name">Version Name</Label>
              <Input
                id="version-name"
                placeholder="1.0.0"
                value={versionName}
                onChange={(e) => setVersionName(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="version-code">Version Code</Label>
              <Input
                id="version-code"
                type="number"
                placeholder="1"
                value={versionCode}
                onChange={(e) => setVersionCode(e.target.value)}
              />
            </div>
          </div>

          {isUploading && (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Upload Progress</span>
                <span className="font-medium">{uploadProgress}%</span>
              </div>
              <Progress value={uploadProgress} />
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={handleClose} disabled={isUploading}>
            Cancel
          </Button>
          <Button onClick={handleUpload} disabled={isUploading || !file || !packageName || !versionName || !versionCode}>
            {isUploading ? (
              <>
                <div className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                Uploading {uploadProgress}%
              </>
            ) : (
              <>
                <Upload className="mr-2 h-4 w-4" />
                Upload
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
