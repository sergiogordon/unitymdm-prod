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
import { AlertTriangle } from "lucide-react"

interface BulkDeleteEnrollmentTokensModalProps {
  isOpen: boolean
  onClose: () => void
  onConfirm: () => Promise<void>
  tokenCount: number
  sampleAliases: string[]
}

export function BulkDeleteEnrollmentTokensModal({
  isOpen,
  onClose,
  onConfirm,
  tokenCount,
  sampleAliases
}: BulkDeleteEnrollmentTokensModalProps) {
  const [confirmText, setConfirmText] = useState("")
  const [isDeleting, setIsDeleting] = useState(false)
  
  const expectedText = `DELETE ${tokenCount}`
  const canDelete = confirmText.trim() === expectedText

  const handleConfirm = async () => {
    if (!canDelete) return
    
    setIsDeleting(true)
    try {
      await onConfirm()
      handleClose()
    } catch (error) {
      console.error("Delete failed:", error)
    } finally {
      setIsDeleting(false)
    }
  }

  const handleClose = () => {
    setConfirmText("")
    onClose()
  }

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-destructive">
            <AlertTriangle className="h-5 w-5" />
            Delete {tokenCount} Enrollment Token{tokenCount !== 1 ? 's' : ''}
          </DialogTitle>
          <DialogDescription className="text-left pt-2">
            This action <strong>cannot be undone</strong>. This will permanently delete the selected enrollment tokens.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {sampleAliases.length > 0 && (
            <div>
              <Label className="text-sm font-medium">Tokens to be deleted:</Label>
              <div className="mt-2 rounded-md border border-border bg-muted/50 p-3">
                <ul className="text-sm space-y-1">
                  {sampleAliases.map((alias, i) => (
                    <li key={i} className="text-muted-foreground">• {alias}</li>
                  ))}
                  {tokenCount > sampleAliases.length && (
                    <li className="text-muted-foreground italic">
                      ... and {tokenCount - sampleAliases.length} more
                    </li>
                  )}
                </ul>
              </div>
            </div>
          )}

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
            {isDeleting ? "Deleting..." : `Delete ${tokenCount} Token${tokenCount !== 1 ? 's' : ''}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
