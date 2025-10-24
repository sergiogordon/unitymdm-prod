"use client"

import { useState, useEffect } from "react"
import { Header } from "@/components/header"
import { PageHeader } from "@/components/page-header"
import { SettingsDrawer } from "@/components/settings-drawer"
import { Monitor } from "lucide-react"
import { Card } from "@/components/ui/card"
import { useTheme } from "@/contexts/ThemeContext"

export default function RemoteControlPage() {
  const { isDark, toggleTheme } = useTheme()
  const [lastUpdated, setLastUpdated] = useState(Date.now())
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)

  const handleRefresh = () => {
    setLastUpdated(Date.now())
  }

  return (
    <div className="min-h-screen">
      <Header
        lastUpdated={lastUpdated}
        alertCount={0}
        isDark={isDark}
        onToggleDark={toggleTheme}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onRefresh={handleRefresh}
      />

      <main className="mx-auto max-w-[1280px] px-6 pb-12 pt-[84px] md:px-8">
        <PageHeader
          icon={<Monitor className="h-8 w-8" />}
          title="Remote Control"
          description="Control and interact with devices remotely through the dashboard."
        />

        <Card className="rounded-2xl border border-border bg-card p-12 text-center shadow-sm">
          <p className="text-muted-foreground">Remote control features coming soon...</p>
        </Card>
      </main>

      <SettingsDrawer isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} />
    </div>
  )
}
