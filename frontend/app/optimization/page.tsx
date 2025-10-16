"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { Header } from "@/components/header"
import { PageHeader } from "@/components/page-header"
import { SettingsDrawer } from "@/components/settings-drawer"
import { Gauge, Check, Plus, Send } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { isAuthenticated } from "@/lib/api-client"

export default function OptimizationPage() {
  const router = useRouter()
  const [isDark, setIsDark] = useState(false)
  const [lastUpdated, setLastUpdated] = useState(Date.now())
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  const [whitelistApps, setWhitelistApps] = useState([{ name: "Speedtest", package: "org.zwanoo.android.speedtest" }])

  // Check authentication
  useEffect(() => {
    if (!isAuthenticated()) {
      router.push('/login')
    }
  }, [router])

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
          icon={<Gauge className="h-8 w-8" />}
          title="Device Optimization"
          description="Manage battery optimization settings and ADB modifications"
        />

        <div className="grid gap-6 lg:grid-cols-2">
          {/* ADB Script Modifications */}
          <Card className="rounded-2xl border border-border bg-card p-6 shadow-sm">
            <div className="mb-6 flex items-center gap-3">
              <div className="rounded-lg bg-muted p-2">
                <Gauge className="h-5 w-5 text-muted-foreground" />
              </div>
              <h2 className="text-lg font-semibold text-card-foreground">ADB Script Modifications</h2>
            </div>
            <p className="mb-6 text-sm text-muted-foreground">
              These optimizations are automatically applied during device enrollment via ADB
            </p>

            <div className="space-y-6">
              <div>
                <h3 className="mb-3 text-sm font-semibold text-card-foreground">Battery Optimizations</h3>
                <div className="space-y-2">
                  {[
                    "Disable Adaptive Battery (adaptive_battery_management_enabled = 0)",
                    "Disable App Standby (app_standby_enabled = 0)",
                    "Disable App Restrictions (app_restriction_enabled = false)",
                    "Disable Dynamic Power Savings (dynamic_power_savings_enabled = 0)",
                  ].map((item) => (
                    <div key={item} className="flex items-start gap-2 text-sm">
                      <Check className="mt-0.5 h-4 w-4 shrink-0 text-green-600 dark:text-green-500" />
                      <span className="text-muted-foreground">{item}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <h3 className="mb-3 text-sm font-semibold text-card-foreground">Performance</h3>
                <div className="space-y-2">
                  {[
                    "Reduce animation scale to 0.5x (window/transition/animator_duration_scale)",
                    "Enable ambient tilt and touch to wake",
                  ].map((item) => (
                    <div key={item} className="flex items-start gap-2 text-sm">
                      <Check className="mt-0.5 h-4 w-4 shrink-0 text-green-600 dark:text-green-500" />
                      <span className="text-muted-foreground">{item}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <h3 className="mb-3 text-sm font-semibold text-card-foreground">Disabled Apps</h3>
                <div className="space-y-2">
                  {[
                    "Verizon bloatware (MyVerizon, APN Library, MIPS Services, etc.)",
                    "Pre-installed games (Candy Crush, Toon Blast, Sudoku, etc.)",
                    "YouTube Music",
                  ].map((item) => (
                    <div key={item} className="flex items-start gap-2 text-sm">
                      <Check className="mt-0.5 h-4 w-4 shrink-0 text-green-600 dark:text-green-500" />
                      <span className="text-muted-foreground">{item}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <h3 className="mb-3 text-sm font-semibold text-card-foreground">Security</h3>
                <div className="space-y-2">
                  {[
                    "Enable installation from unknown sources",
                    "Enabled Verizon device management (dmclientupdate, obdm)",
                  ].map((item) => (
                    <div key={item} className="flex items-start gap-2 text-sm">
                      <Check className="mt-0.5 h-4 w-4 shrink-0 text-green-600 dark:text-green-500" />
                      <span className="text-muted-foreground">{item}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </Card>

          {/* Battery Optimization Whitelist */}
          <Card className="rounded-2xl border border-border bg-card p-6 shadow-sm">
            <div className="mb-6 flex items-center gap-3">
              <div className="rounded-lg bg-green-500/10 p-2">
                <Gauge className="h-5 w-5 text-green-600 dark:text-green-500" />
              </div>
              <h2 className="text-lg font-semibold text-card-foreground">Battery Optimization Whitelist</h2>
            </div>
            <p className="mb-6 text-sm text-muted-foreground">
              Apps exempt from Android's battery optimization and Doze mode
            </p>

            <div className="mb-4 flex gap-2">
              <Button size="sm" className="gap-2">
                <Plus className="h-4 w-4" />
                Add App
              </Button>
              <Button size="sm" variant="outline" className="gap-2 bg-transparent">
                <Send className="h-4 w-4" />
                Apply to Fleet
              </Button>
            </div>

            <div className="overflow-hidden rounded-lg border border-border">
              <table className="w-full">
                <thead className="border-b border-border bg-muted/50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground">App Name</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground">Package Name</th>
                  </tr>
                </thead>
                <tbody>
                  {whitelistApps.map((app, index) => (
                    <tr key={index} className="border-b border-border last:border-0">
                      <td className="px-4 py-3 text-sm text-card-foreground">{app.name}</td>
                      <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{app.package}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      </main>

      <SettingsDrawer isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} />
    </div>
  )
}
