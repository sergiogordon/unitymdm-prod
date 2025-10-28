"use client"

import { usePathname } from "next/navigation"
import { Sidebar } from "@/components/sidebar"
import { useAuth } from "@/lib/auth"
import { ReactNode } from "react"
import { useSettings } from "@/contexts/SettingsContext"
import { SettingsDrawer } from "@/components/settings-drawer"

export function ConditionalSidebar({ children }: { children?: ReactNode }) {
  const pathname = usePathname()
  const { isAuthenticated } = useAuth()
  const { isSettingsOpen, closeSettings } = useSettings()

  const shouldShowSidebar = isAuthenticated && pathname !== '/login'

  if (!shouldShowSidebar) {
    return <>{children}</>
  }

  return (
    <>
      <Sidebar />
      <div className="pl-64">{children}</div>
      <SettingsDrawer isOpen={isSettingsOpen} onClose={closeSettings} />
    </>
  )
}
