"use client"

import { Trash2, X } from "lucide-react"
import { Button } from "@/components/ui/button"

interface BulkActionsBarProps {
  selectedCount: number
  onDelete: () => void
  onClear: () => void
}

export function BulkActionsBar({ selectedCount, onDelete, onClear }: BulkActionsBarProps) {
  if (selectedCount === 0) return null

  return (
    <div className="sticky bottom-0 left-0 right-0 z-40 border-t border-border bg-card/95 backdrop-blur supports-[backdrop-filter]:bg-card/60">
      <div className="flex items-center justify-between px-6 py-4">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center">
              <span className="text-sm font-semibold text-primary">{selectedCount}</span>
            </div>
            <span className="text-sm font-medium">
              {selectedCount} device{selectedCount !== 1 ? 's' : ''} selected
            </span>
          </div>
        </div>
        
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={onClear}>
            <X className="h-4 w-4 mr-2" />
            Clear selection
          </Button>
          <Button variant="destructive" size="sm" onClick={onDelete}>
            <Trash2 className="h-4 w-4 mr-2" />
            Delete {selectedCount} device{selectedCount !== 1 ? 's' : ''}
          </Button>
        </div>
      </div>
    </div>
  )
}
