"use client"

import { ReactNode, useState, useEffect } from "react"
import { Header } from "@/components/header"
import { Sidebar } from "@/components/sidebar"
import { SettingsDrawer } from "@/components/settings-drawer"
import { useTheme } from "@/contexts/ThemeContext"

interface PageWrapperProps {
  children: ReactNode
  lastUpdated?: number
  alertCount?: number
  onRefresh?: () => void
}

export function PageWrapper({ children, lastUpdated = Date.now(), alertCount = 0, onRefresh = () => {} }: PageWrapperProps) {
  const { isDark, toggleTheme } = useTheme()
  const [isSidebarOpen, setIsSidebarOpen] = useState(true)
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)

  useEffect(() => {
    const sidebarOpen = localStorage.getItem('sidebarOpen')
    if (sidebarOpen !== null) {
      setIsSidebarOpen(sidebarOpen === 'true')
    }
  }, [])

  const handleToggleSidebar = () => {
    const newState = !isSidebarOpen
    setIsSidebarOpen(newState)
    localStorage.setItem('sidebarOpen', newState.toString())
  }

  return (
    <div className="min-h-screen">
      <Sidebar isOpen={isSidebarOpen} onToggle={handleToggleSidebar} />
      
      <Header
        lastUpdated={lastUpdated}
        alertCount={alertCount}
        isDark={isDark}
        onToggleDark={toggleTheme}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onRefresh={onRefresh}
        onToggleSidebar={handleToggleSidebar}
      />

      <main className={`transition-all duration-300 px-6 pb-12 pt-[84px] md:px-8 ${isSidebarOpen ? 'lg:ml-64' : 'lg:ml-16'}`}>
        {children}
      </main>

      <SettingsDrawer
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
      />
    </div>
  )
}
