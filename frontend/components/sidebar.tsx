"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { LayoutGrid, Package, Terminal, Monitor, Rocket, Gauge, ChevronLeft, Settings, Wifi, Users } from "lucide-react"
import { cn } from "@/lib/utils"
import { useState } from "react"
import { useSettings } from "@/contexts/SettingsContext"

const navigation = [
  { name: "Dashboard", href: "/", icon: LayoutGrid },
  { name: "APK Management", href: "/apk-management", icon: Package },
  { name: "ADB Setup", href: "/adb-setup", icon: Terminal },
  { name: "Batch Enroll", href: "/batch-enroll", icon: Users },
  { name: "Remote Control", href: "/remote-control", icon: Monitor },
  { name: "Launch App", href: "/launch-app", icon: Rocket },
  { name: "WiFi Push", href: "/wifi-push", icon: Wifi },
  { name: "Optimization", href: "/device-optimization", icon: Gauge },
  { name: "Remote Execution", href: "/remote-execution", icon: Terminal },
]

export function Sidebar() {
  const pathname = usePathname()
  const [isCollapsed, setIsCollapsed] = useState(false)
  const { openSettings } = useSettings()

  return (
    <aside
      className={cn(
        "fixed left-0 top-0 z-40 h-screen border-r border-sidebar-border bg-sidebar transition-all duration-300",
        isCollapsed ? "w-16" : "w-64",
      )}
    >
      <div className="flex h-16 items-center justify-between border-b border-sidebar-border px-4">
        {!isCollapsed && (
          <div className="flex items-center">
            {/* Light mode logo (black) */}
            <svg
              className="h-8 w-auto dark:hidden"
              width="98"
              height="113"
              viewBox="0 0 98 113"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                d="M9.49566 63.8018C9.49566 85.6787 27.2931 103.476 49.1699 103.476C71.0469 103.476 88.8442 85.6788 88.8442 63.8018V0.711792H97.6562V63.8018C97.6562 90.5369 75.905 112.288 49.1699 112.288C22.435 112.288 0.683594 90.5368 0.683594 63.8018V0.711792H9.49566V63.8018Z"
                fill="black"
              />
              <path
                d="M27.1248 62.5358C27.126 74.6894 37.0173 84.571 49.1649 84.571C61.3126 84.571 71.2039 74.6894 71.2051 62.5358V0.711792H80.0172V62.5358C80.016 79.5471 66.1776 93.3924 49.16 93.3931L49.1699 93.3881C32.1578 93.3874 18.3127 79.5443 18.3127 62.5259V0.711792H27.1248V62.5358Z"
                fill="black"
              />
              <path
                d="M44.7589 61.3446C44.7589 63.7764 46.7383 65.755 49.1699 65.7556C51.6021 65.7556 53.5809 63.7768 53.5809 61.3446V0.711792H62.398V61.3446C62.398 68.6349 56.4602 74.5677 49.1699 74.5677C41.8802 74.5671 35.9468 68.6345 35.9468 61.3446V0.711792H44.7589V61.3446Z"
                fill="black"
              />
            </svg>
            {/* Dark mode logo (white) */}
            <svg
              className="hidden h-8 w-auto dark:block"
              width="98"
              height="113"
              viewBox="0 0 98 113"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                d="M9.49566 63.8018C9.49566 85.6787 27.2931 103.476 49.1699 103.476C71.0469 103.476 88.8442 85.6788 88.8442 63.8018V0.711792H97.6562V63.8018C97.6562 90.5369 75.905 112.288 49.1699 112.288C22.435 112.288 0.683594 90.5368 0.683594 63.8018V0.711792H9.49566V63.8018Z"
                fill="white"
              />
              <path
                d="M27.1248 62.5358C27.126 74.6894 37.0173 84.571 49.1649 84.571C61.3126 84.571 71.2039 74.6894 71.2051 62.5358V0.711792H80.0172V62.5358C80.016 79.5471 66.1776 93.3924 49.16 93.3931L49.1699 93.3881C32.1578 93.3874 18.3127 79.5443 18.3127 62.5259V0.711792H27.1248V62.5358Z"
                fill="white"
              />
              <path
                d="M44.7589 61.3446C44.7589 63.7764 46.7383 65.755 49.1699 65.7556C51.6021 65.7556 53.5809 63.7768 53.5809 61.3446V0.711792H62.398V61.3446C62.398 68.6349 56.4602 74.5677 49.1699 74.5677C41.8802 74.5671 35.9468 68.6345 35.9468 61.3446V0.711792H44.7589V61.3446Z"
                fill="white"
              />
            </svg>
          </div>
        )}
        <button
          onClick={() => setIsCollapsed(!isCollapsed)}
          className="rounded-lg p-1.5 text-sidebar-foreground/60 transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
          aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <ChevronLeft className={cn("h-5 w-5 transition-transform", isCollapsed && "rotate-180")} />
        </button>
      </div>

      <nav className="flex flex-col h-[calc(100vh-4rem)]">
        <div className="space-y-1 p-3 flex-1">
          {navigation.map((item) => {
            const isActive = pathname === item.href
            const Icon = item.icon

            return (
              <Link
                key={item.name}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-sidebar-primary text-sidebar-primary-foreground"
                    : "text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                )}
                title={isCollapsed ? item.name : undefined}
              >
                <Icon className="h-5 w-5 shrink-0" />
                {!isCollapsed && <span>{item.name}</span>}
              </Link>
            )
          })}
        </div>
        
        <div className="border-t border-sidebar-border p-3">
          <button
            onClick={openSettings}
            className={cn(
              "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
              "text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
            )}
            title={isCollapsed ? "Settings" : undefined}
          >
            <Settings className="h-5 w-5 shrink-0" />
            {!isCollapsed && <span>Settings</span>}
          </button>
        </div>
      </nav>
    </aside>
  )
}
