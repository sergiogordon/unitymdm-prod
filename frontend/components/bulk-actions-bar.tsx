"use client"

import { Trash2, X, Radio, Bell, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"

export interface BulkActionProgress {
  action: 'ping' | 'ring'
  total: number
  completed: number
  failed: number
  inProgress: boolean
}

interface BulkActionsBarProps {
  selectedCount: number
  onDelete: () => void
  onClear: () => void
  onBulkPing?: () => void
  onBulkRing?: () => void
  bulkActionProgress?: BulkActionProgress | null
}

export function BulkActionsBar({ 
  selectedCount, 
  onDelete, 
  onClear, 
  onBulkPing, 
  onBulkRing,
  bulkActionProgress 
}: BulkActionsBarProps) {
  if (selectedCount === 0) return null

  const isActionInProgress = bulkActionProgress?.inProgress ?? false
  const progressPercentage = bulkActionProgress 
    ? Math.round(((bulkActionProgress.completed + bulkActionProgress.failed) / bulkActionProgress.total) * 100)
    : 0

  return (
    <div className="sticky bottom-0 left-0 right-0 z-40 border-t border-border bg-card/95 backdrop-blur supports-[backdrop-filter]:bg-card/60">
      <div className="flex flex-col gap-2 px-6 py-4">
        {bulkActionProgress?.inProgress && (
          <div className="flex items-center gap-4">
            <div className="flex-1">
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium">
                  {bulkActionProgress.action === 'ping' ? 'Pinging' : 'Ringing'} devices...
                </span>
                <span className="text-sm text-muted-foreground">
                  {bulkActionProgress.completed + bulkActionProgress.failed}/{bulkActionProgress.total}
                  {bulkActionProgress.failed > 0 && (
                    <span className="text-destructive ml-1">({bulkActionProgress.failed} failed)</span>
                  )}
                </span>
              </div>
              <Progress value={progressPercentage} className="h-2" />
            </div>
          </div>
        )}
        
        <div className="flex items-center justify-between">
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
            <Button 
              variant="outline" 
              size="sm" 
              onClick={onClear}
              disabled={isActionInProgress}
            >
              <X className="h-4 w-4 mr-2" />
              Clear selection
            </Button>
            
            {onBulkPing && (
              <Button 
                variant="outline" 
                size="sm" 
                onClick={onBulkPing}
                disabled={isActionInProgress}
              >
                {isActionInProgress && bulkActionProgress?.action === 'ping' ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Radio className="h-4 w-4 mr-2" />
                )}
                Ping {selectedCount} device{selectedCount !== 1 ? 's' : ''}
              </Button>
            )}
            
            {onBulkRing && (
              <Button 
                variant="outline" 
                size="sm" 
                onClick={onBulkRing}
                disabled={isActionInProgress}
              >
                {isActionInProgress && bulkActionProgress?.action === 'ring' ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Bell className="h-4 w-4 mr-2" />
                )}
                Ring {selectedCount} device{selectedCount !== 1 ? 's' : ''}
              </Button>
            )}
            
            <Button 
              variant="destructive" 
              size="sm" 
              onClick={onDelete}
              disabled={isActionInProgress}
            >
              <Trash2 className="h-4 w-4 mr-2" />
              Delete {selectedCount} device{selectedCount !== 1 ? 's' : ''}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
