"use client"

import { useState, useEffect } from "react"
import { Settings } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"

interface DashboardHeaderProps {
  lastUpdated: number
  alertCount: number
  onOpenSettings: () => void
  onRefresh: () => void
  className?: string
}

export function DashboardHeader({
  lastUpdated,
  alertCount,
  onOpenSettings,
  onRefresh,
  className,
}: DashboardHeaderProps) {
  const [timeAgo, setTimeAgo] = useState("0s ago")
  const [shouldPulse, setShouldPulse] = useState(false)

  useEffect(() => {
    const updateTimeAgo = () => {
      const seconds = Math.floor((Date.now() - lastUpdated) / 1000)
      if (seconds < 60) {
        setTimeAgo(`${seconds}s ago`)
      } else {
        const minutes = Math.floor(seconds / 60)
        setTimeAgo(`${minutes}m ago`)
      }
    }

    updateTimeAgo()
    const interval = setInterval(updateTimeAgo, 1000)
    return () => clearInterval(interval)
  }, [lastUpdated])

  useEffect(() => {
    setShouldPulse(true)
    const timeout = setTimeout(() => setShouldPulse(false), 600)
    return () => clearTimeout(timeout)
  }, [lastUpdated])

  return (
    <div
      className={cn(
        "sticky top-[60px] z-40 -mx-6 mb-6 border-b border-border/40 bg-background/95 px-6 backdrop-blur supports-[backdrop-filter]:bg-background/60 md:-mx-8 md:px-8",
        className,
      )}
    >
      <div className="flex min-h-14 flex-wrap items-center justify-end gap-3 py-2 sm:flex-nowrap sm:gap-4 sm:py-0">
        {/* Updated and Alerts metadata */}
        <div className="flex items-center gap-3 sm:gap-4">
          <button
            onClick={onRefresh}
            className="flex items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 rounded-sm"
            aria-label="Refresh dashboard data"
          >
            <span className="hidden sm:inline">Updated</span>
            <span className="sm:hidden">Updated</span>
            <span className="text-foreground">•</span>
            <span className={shouldPulse ? "animate-pulse-once" : ""}>{timeAgo}</span>
          </button>

          <div className="flex items-center gap-1.5 rounded-full bg-muted px-3 py-1.5 text-sm">
            <span className="text-muted-foreground">Alerts</span>
            <span className="text-foreground">•</span>
            <span className={alertCount > 0 ? "font-medium text-status-offline" : ""}>{alertCount}</span>
          </div>
        </div>

        {/* Right side: Settings gear - aligned with table right edge */}
        <div className="flex items-center">
          <TooltipProvider delayDuration={300}>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={onOpenSettings}
                  className="h-10 w-10"
                  aria-label="Settings"
                  role="button"
                >
                  <Settings className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="bottom">
                <p>Settings</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
      </div>
    </div>
  )
}
