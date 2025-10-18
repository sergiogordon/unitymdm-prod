"use client"

import { useState, useEffect } from "react"
import { Monitor } from "lucide-react"
import { Header } from "@/components/header"
import { Sidebar } from "@/components/sidebar"
import { SettingsDrawer } from "@/components/settings-drawer"

export default function DemoRemoteControlPage() {
  const [isDark, setIsDark] = useState(false)
  const [isSidebarOpen, setIsSidebarOpen] = useState(true)
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  const [lastUpdated] = useState(Date.now())

  useEffect(() => {
    const isDarkMode = localStorage.getItem('darkMode') === 'true'
    setIsDark(isDarkMode)
    if (isDarkMode) {
      document.documentElement.classList.add("dark")
    } else {
      document.documentElement.classList.remove("dark")
    }
  }, [])

  const handleToggleDark = () => {
    const newDark = !isDark
    setIsDark(newDark)
    localStorage.setItem('darkMode', newDark.toString())
  }

  const handleToggleSidebar = () => {
    setIsSidebarOpen(!isSidebarOpen)
  }

  return (
    <div className="min-h-screen">
      <Sidebar isOpen={isSidebarOpen} onToggle={handleToggleSidebar} />
      
      <Header
        lastUpdated={lastUpdated}
        alertCount={0}
        isDark={isDark}
        onToggleDark={handleToggleDark}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onRefresh={() => {}}
        onToggleSidebar={handleToggleSidebar}
      />

      <main className={`transition-all duration-300 mx-auto max-w-[1600px] px-6 pb-12 pt-20 md:px-8 ${isSidebarOpen ? 'lg:ml-64' : 'lg:ml-16'}`}>
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">Remote Control</h2>
            <p className="mt-1 text-sm text-muted-foreground">View and control devices remotely</p>
          </div>
        </div>

        <div className="flex flex-col items-center justify-center py-16 text-center space-y-6">
          <div className="rounded-full bg-muted p-6">
            <Monitor className="h-16 w-16 text-muted-foreground" />
          </div>
          <div className="space-y-2">
            <h3 className="text-xl font-medium">Remote Control Not Available in Demo</h3>
            <p className="text-sm text-muted-foreground max-w-md">
              Remote control and screen streaming features require real device connections. 
              In production, this page allows you to view and control device screens in real-time.
            </p>
          </div>
          <div className="rounded-lg border border-border/40 bg-card p-6 max-w-2xl text-left">
            <h4 className="text-sm font-medium mb-3">Production Features:</h4>
            <ul className="list-disc list-inside space-y-2 text-sm text-muted-foreground">
              <li>Live screen streaming at 720p JPEG @ ~10 FPS</li>
              <li>Interactive canvas for tap, swipe, and text input</li>
              <li>Navigation controls (home, back, recents)</li>
              <li>Real-time FPS and latency metrics</li>
              <li>Fullscreen mode for better viewing</li>
              <li>Bidirectional clipboard synchronization</li>
            </ul>
          </div>
        </div>
      </main>

      <SettingsDrawer 
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
      />
    </div>
  )
}
