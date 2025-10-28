"use client"

import { usePathname } from "next/navigation"
import { Sidebar } from "@/components/sidebar"
import { useAuth } from "@/lib/auth"
import { ReactNode } from "react"
import { SettingsProvider, useSettings } from "@/contexts/SettingsContext"
import { SettingsDrawer } from "@/components/settings-drawer"

function SidebarLayout({ children }: { children?: ReactNode }) {
  const { isSettingsOpen, closeSettings } = useSettings()

  return (
    <>
      <Sidebar />
      <div className="pl-64">{children}</div>
      <SettingsDrawer isOpen={isSettingsOpen} onClose={closeSettings} />
    </>
  )
}

function ConditionalSidebarContent({ children }: { children?: ReactNode }) {
  const pathname = usePathname()
  const { isAuthenticated } = useAuth()

  const shouldShowSidebar = isAuthenticated && pathname !== '/login'

  if (!shouldShowSidebar) {
    return <>{children}</>
  }

  return (
    <SettingsProvider>
      <SidebarLayout>{children}</SidebarLayout>
    </SettingsProvider>
  )
}

export function ConditionalSidebar({ children }: { children?: ReactNode }) {
  return <ConditionalSidebarContent>{children}</ConditionalSidebarContent>
}
