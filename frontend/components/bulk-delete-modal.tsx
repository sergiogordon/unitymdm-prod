"use client"

import { useState } from "react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Checkbox } from "@/components/ui/checkbox"
import { AlertTriangle } from "lucide-react"

interface BulkDeleteModalProps {
  isOpen: boolean
  onClose: () => void
  onConfirm: (purgeHistory: boolean) => Promise<void>
  deviceCount: number
  sampleAliases: string[]
}

export function BulkDeleteModal({
  isOpen,
  onClose,
  onConfirm,
  deviceCount,
  sampleAliases
}: BulkDeleteModalProps) {
  const [confirmText, setConfirmText] = useState("")
  const [purgeHistory, setPurgeHistory] = useState(true)
  const [isDeleting, setIsDeleting] = useState(false)
  
  const expectedText = `DELETE ${deviceCount}`
  const canDelete = confirmText.trim() === expectedText

  const handleConfirm = async () => {
    if (!canDelete) return
    
    setIsDeleting(true)
    try {
      await onConfirm(purgeHistory)
      handleClose()
    } catch (error) {
      console.error("Delete failed:", error)
    } finally {
      setIsDeleting(false)
    }
  }

  const handleClose = () => {
    setConfirmText("")
    setPurgeHistory(true)
    onClose()
  }

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-destructive">
            <AlertTriangle className="h-5 w-5" />
            Delete {deviceCount} Device{deviceCount !== 1 ? 's' : ''}
          </DialogTitle>
          <DialogDescription className="text-left pt-2">
            This action <strong>cannot be undone</strong>. This will permanently delete the selected devices and all associated data.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Sample devices */}
          {sampleAliases.length > 0 && (
            <div>
              <Label className="text-sm font-medium">Devices to be deleted:</Label>
              <div className="mt-2 rounded-md border border-border bg-muted/50 p-3">
                <ul className="text-sm space-y-1">
                  {sampleAliases.map((alias, i) => (
                    <li key={i} className="text-muted-foreground">• {alias}</li>
                  ))}
                  {deviceCount > sampleAliases.length && (
                    <li className="text-muted-foreground italic">
                      ... and {deviceCount - sampleAliases.length} more
                    </li>
                  )}
                </ul>
              </div>
            </div>
          )}

          {/* Purge history checkbox */}
          <div className="flex items-start space-x-2 rounded-md border border-border bg-card p-3">
            <Checkbox
              id="purge-history"
              checked={purgeHistory}
              onCheckedChange={(checked) => setPurgeHistory(checked === true)}
            />
            <div className="grid gap-1.5 leading-none">
              <label
                htmlFor="purge-history"
                className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
              >
                Also delete historical telemetry
              </label>
              <p className="text-xs text-muted-foreground">
                Remove all heartbeat logs and dispatch history for these devices
              </p>
            </div>
          </div>

          {/* Type to confirm */}
          <div>
            <Label htmlFor="confirm-text" className="text-sm font-medium">
              Type <code className="relative rounded bg-muted px-[0.3rem] py-[0.2rem] font-mono text-sm">{expectedText}</code> to confirm
            </Label>
            <Input
              id="confirm-text"
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder={expectedText}
              className="mt-2 font-mono"
              disabled={isDeleting}
              autoComplete="off"
            />
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={handleClose}
            disabled={isDeleting}
          >
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleConfirm}
            disabled={!canDelete || isDeleting}
          >
            {isDeleting ? "Deleting..." : `Delete ${deviceCount} Device${deviceCount !== 1 ? 's' : ''}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
