"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { 
  LayoutDashboard, 
  Package, 
  Terminal, 
  Monitor, 
  Rocket, 
  Battery,
  ChevronLeft,
  Menu
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

interface SidebarProps {
  isOpen: boolean
  onToggle: () => void
}

const navigationItems = [
  { href: "/", icon: LayoutDashboard, label: "Dashboard" },
  { href: "/apk-management", icon: Package, label: "APK Management" },
  { href: "/adb-setup", icon: Terminal, label: "ADB Setup" },
  { href: "/remote-control", icon: Monitor, label: "Remote Control" },
  { href: "/launch-app", icon: Rocket, label: "Launch App" },
  { href: "/device-optimization", icon: Battery, label: "Optimization" },
]

export function Sidebar({ isOpen, onToggle }: SidebarProps) {
  const pathname = usePathname()
  const isDemoMode = pathname.startsWith('/demo')
  const baseHref = isDemoMode ? '/demo' : ''

  const navItems = navigationItems.map(item => ({
    ...item,
    href: item.href === '/' ? (isDemoMode ? '/demo' : '/') : `${baseHref}${item.href}`
  }))

  return (
    <>
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={onToggle}
        />
      )}

      <aside
        className={cn(
          "fixed left-0 top-0 z-50 h-full bg-background/95 backdrop-blur-xl border-r border-border/40 transition-all duration-300 ease-in-out",
          isOpen ? "w-64" : "w-0 lg:w-16",
          "lg:translate-x-0",
          isOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
        )}
      >
        <div className="flex flex-col h-full">
          <div className="flex items-center justify-between h-[60px] px-4 border-b border-border/40">
            {isOpen && (
              <Link href="/" className="flex items-center gap-2">
                <h1 className="text-lg font-semibold tracking-tight">UNITYmdm</h1>
              </Link>
            )}
            <Button
              variant="ghost"
              size="icon"
              onClick={onToggle}
              className={cn(
                "h-8 w-8 flex-shrink-0",
                !isOpen && "hidden lg:flex"
              )}
            >
              {isOpen ? (
                <ChevronLeft className="h-4 w-4" />
              ) : (
                <Menu className="h-4 w-4" />
              )}
            </Button>
          </div>

          <nav className="flex-1 overflow-y-auto py-4 px-2">
            <div className="space-y-1">
              {navItems.map((item) => {
                const Icon = item.icon
                const isActive = pathname === item.href

                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    prefetch={true}
                    onClick={() => {
                      if (window.innerWidth < 1024) {
                        onToggle()
                      }
                    }}
                  >
                    <div
                      className={cn(
                        "flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors",
                        "hover:bg-muted/50",
                        isActive && "bg-muted text-foreground",
                        !isActive && "text-muted-foreground"
                      )}
                    >
                      <Icon className="h-5 w-5 flex-shrink-0" />
                      {isOpen && (
                        <span className="text-sm font-medium whitespace-nowrap">
                          {item.label}
                        </span>
                      )}
                    </div>
                  </Link>
                )
              })}
            </div>
          </nav>

          {!isOpen && (
            <div className="hidden lg:flex items-center justify-center py-4 border-t border-border/40">
              <Button
                variant="ghost"
                size="icon"
                onClick={onToggle}
                className="h-8 w-8"
              >
                <Menu className="h-4 w-4" />
              </Button>
            </div>
          )}
        </div>
      </aside>
    </>
  )
}
