"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { Header } from "@/components/header"
import { PageHeader } from "@/components/page-header"
import { Gauge, Check, Plus, Send, Package } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { isAuthenticated, updateBloatwareList } from "@/lib/api-client"
import { useToast } from "@/hooks/use-toast"

export default function OptimizationPage() {
  const router = useRouter()
  const { toast } = useToast()
  const [isDark, setIsDark] = useState(false)
  const [whitelistApps, setWhitelistApps] = useState([{ name: "Speedtest", package: "org.zwanoo.android.speedtest" }])
  const [bloatwarePackages, setBloatwarePackages] = useState("")
  const [isSavingBloatware, setIsSavingBloatware] = useState(false)

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

  const handleSaveBloatware = async () => {
    setIsSavingBloatware(true)
    try {
      // Parse packages (one per line, trim whitespace)
      const packages = bloatwarePackages
        .split('\n')
        .map(line => line.trim())
        .filter(line => line.length > 0)
      
      if (packages.length === 0) {
        toast({
          title: "Error",
          description: "Please enter at least one package name",
          variant: "destructive"
        })
        return
      }

      await updateBloatwareList(packages)
      
      toast({
        title: "Success",
        description: `Updated bloatware list with ${packages.length} packages`
      })
    } catch (error: any) {
      toast({
        title: "Error",
        description: error.message || "Failed to update bloatware list",
        variant: "destructive"
      })
    } finally {
      setIsSavingBloatware(false)
    }
  }

  return (
    <div className="min-h-screen">
      <Header
        isDark={isDark}
        onToggleDark={() => setIsDark(!isDark)}
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

        {/* Bloatware Management Section */}
        <Card className="mt-6 rounded-2xl border border-border bg-card p-6 shadow-sm">
          <div className="mb-6 flex items-center gap-3">
            <div className="rounded-lg bg-red-500/10 p-2">
              <Package className="h-5 w-5 text-red-600 dark:text-red-500" />
            </div>
            <h2 className="text-lg font-semibold text-card-foreground">Bloatware Management</h2>
          </div>
          <p className="mb-6 text-sm text-muted-foreground">
            Manage the global list of bloatware packages that will be automatically disabled during device enrollment. 
            Enter one package name per line. This list applies to all new device enrollments.
          </p>

          <div className="space-y-4">
            <Textarea
              value={bloatwarePackages}
              onChange={(e) => setBloatwarePackages(e.target.value)}
              placeholder="com.example.bloatware&#10;com.vzw.hss.myverizon&#10;com.google.android.youtube&#10;..."
              className="min-h-[300px] font-mono text-xs"
            />
            
            <div className="flex items-center justify-between">
              <p className="text-xs text-muted-foreground">
                {bloatwarePackages.split('\n').filter(line => line.trim().length > 0).length} packages
              </p>
              <Button 
                onClick={handleSaveBloatware}
                disabled={isSavingBloatware}
                className="gap-2"
              >
                {isSavingBloatware ? "Saving..." : "Save Bloatware List"}
              </Button>
            </div>
          </div>
        </Card>
      </main>
    </div>
  )
}
