"use client"

import { useState, useEffect } from "react"
import { Moon, Sun, Settings, RefreshCw, Menu } from "lucide-react"
import { Button } from "@/components/ui/button"
import Link from "next/link"

interface HeaderProps {
  lastUpdated: number
  alertCount: number
  isDark: boolean
  onToggleDark: () => void
  onOpenSettings: () => void
  onRefresh: () => void
  onToggleSidebar: () => void
}

export function Header({ lastUpdated, alertCount, isDark, onToggleDark, onOpenSettings, onRefresh, onToggleSidebar }: HeaderProps) {
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
    <header className="fixed top-0 z-40 w-full border-b border-border/40 bg-background/80 backdrop-blur-xl transition-all">
      <div className="flex h-[60px] items-center justify-between px-4 md:px-6">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="icon"
            onClick={onToggleSidebar}
            className="h-9 w-9 lg:hidden"
          >
            <Menu className="h-5 w-5" />
          </Button>
          
          <Link href="/" className="lg:hidden">
            <h1 className="text-lg font-semibold tracking-tight">UNITYmdm</h1>
          </Link>
        </div>

        <div className="flex items-center gap-2 md:gap-4">
          <button
            onClick={onRefresh}
            className="hidden md:flex items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            <span>Updated</span>
            <span className="text-foreground">•</span>
            <span className={shouldPulse ? "animate-pulse-once" : ""}>{timeAgo}</span>
          </button>

          <button
            onClick={onRefresh}
            className="md:hidden flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            <span className={shouldPulse ? "animate-pulse-once" : ""}>{timeAgo}</span>
          </button>

          <div className="hidden md:flex items-center gap-1.5 rounded-full bg-muted px-3 py-1.5 text-sm">
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
