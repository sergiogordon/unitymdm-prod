"use client"

import { useState, useEffect } from "react"
import { Header } from "@/components/header"
import { PageHeader } from "@/components/page-header"
import { SettingsDrawer } from "@/components/settings-drawer"
import { Rocket } from "lucide-react"
import { Card } from "@/components/ui/card"

export default function LaunchAppPage() {
  const [isDark, setIsDark] = useState(false)
  const [lastUpdated, setLastUpdated] = useState(Date.now())
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)

  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add("dark")
    } else {
      document.documentElement.classList.remove("dark")
    }
  }, [isDark])

  const handleRefresh = () => {
    setLastUpdated(Date.now())
  }

  return (
    <div className="min-h-screen">
      <Header
        lastUpdated={lastUpdated}
        alertCount={0}
        isDark={isDark}
        onToggleDark={() => setIsDark(!isDark)}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onRefresh={handleRefresh}
      />

      <main className="mx-auto max-w-[1280px] px-6 pb-12 pt-[84px] md:px-8">
        <PageHeader
          icon={<Rocket className="h-8 w-8" />}
          title="Launch App"
          description="Remotely launch applications on managed devices."
        />

        <Card className="rounded-2xl border border-border bg-card p-12 text-center shadow-sm">
          <p className="text-muted-foreground">Launch app features coming soon...</p>
        </Card>
      </main>

      <SettingsDrawer isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} />
    </div>
  )
}
