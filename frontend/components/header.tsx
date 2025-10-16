"use client"

import { useState, useEffect } from "react"
import { Moon, Sun, Settings } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

interface HeaderProps {
  lastUpdated: number
  alertCount: number
  isDark: boolean
  onToggleDark: () => void
  onOpenSettings: () => void
  onRefresh: () => void
  className?: string
}

export function Header({
  lastUpdated,
  alertCount,
  isDark,
  onToggleDark,
  onOpenSettings,
  onRefresh,
  className,
}: HeaderProps) {
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
    <header
      className={cn("fixed top-0 z-50 w-full border-b border-border/40 bg-background/80 backdrop-blur-xl", className)}
    >
      <div className="mx-auto flex h-[60px] max-w-[1280px] items-center justify-between px-6 md:px-8">
        <h1 className="text-lg font-semibold tracking-tight">Unity Micro-MDM</h1>

        <div className="flex items-center gap-4">
          <button
            onClick={onRefresh}
            className="flex items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <span>Updated</span>
            <span className="text-foreground">•</span>
            <span className={shouldPulse ? "animate-pulse-once" : ""}>{timeAgo}</span>
          </button>

          <div className="flex items-center gap-1.5 rounded-full bg-muted px-3 py-1.5 text-sm">
            <span className="text-muted-foreground">Alerts</span>
            <span className="text-foreground">•</span>
            <span className={alertCount > 0 ? "font-medium text-status-offline" : ""}>{alertCount}</span>
          </div>

          <Button variant="ghost" size="icon" onClick={onToggleDark} className="h-9 w-9">
            {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>

          <Button variant="ghost" size="icon" onClick={onOpenSettings} className="h-9 w-9">
            <Settings className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </header>
  )
}
