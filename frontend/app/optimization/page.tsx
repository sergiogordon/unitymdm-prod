"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { Header } from "@/components/header"
import { PageHeader } from "@/components/page-header"
import { Gauge, Check, Plus, Send, Package, Trash2, RotateCcw, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { isAuthenticated, getBloatwareList, addBloatwarePackage, deleteBloatwarePackage, resetBloatwareList } from "@/lib/api-client"
import { useToast } from "@/hooks/use-toast"
import { useTheme } from "@/contexts/ThemeContext"

export default function OptimizationPage() {
  const router = useRouter()
  const { toast } = useToast()
  const { isDark, toggleTheme } = useTheme()
  const [whitelistApps, setWhitelistApps] = useState([{ name: "Speedtest", package: "org.zwanoo.android.speedtest" }])
  const [bloatwarePackages, setBloatwarePackages] = useState<Array<{ id: number; package_name: string; enabled: boolean }>>([])
  const [isLoadingBloatware, setIsLoadingBloatware] = useState(true)
  const [newPackageName, setNewPackageName] = useState("")
  const [isAddingPackage, setIsAddingPackage] = useState(false)

  // Check authentication
  useEffect(() => {
    if (!isAuthenticated()) {
      router.push('/login')
    }
  }, [router])

  // Load bloatware packages on mount
  useEffect(() => {
    loadBloatwarePackages()
  }, [])

  const loadBloatwarePackages = async () => {
    setIsLoadingBloatware(true)
    try {
      const data = await getBloatwareList()
      setBloatwarePackages(data.packages)
    } catch (error: any) {
      toast({
        title: "Error",
        description: error.message || "Failed to load bloatware list",
        variant: "destructive"
      })
    } finally {
      setIsLoadingBloatware(false)
    }
  }

  const handleAddPackage = async () => {
    if (!newPackageName.trim()) {
      toast({
        title: "Error",
        description: "Please enter a package name",
        variant: "destructive"
      })
      return
    }

    setIsAddingPackage(true)
    try {
      await addBloatwarePackage(newPackageName.trim())
      toast({
        title: "Success",
        description: `Added package ${newPackageName.trim()}`
      })
      setNewPackageName("")
      await loadBloatwarePackages()
    } catch (error: any) {
      toast({
        title: "Error",
        description: error.message || "Failed to add package",
        variant: "destructive"
      })
    } finally {
      setIsAddingPackage(false)
    }
  }

  const handleDeletePackage = async (packageName: string) => {
    try {
      await deleteBloatwarePackage(packageName)
      toast({
        title: "Success",
        description: `Deleted package ${packageName}`
      })
      await loadBloatwarePackages()
    } catch (error: any) {
      toast({
        title: "Error",
        description: error.message || "Failed to delete package",
        variant: "destructive"
      })
    }
  }

  const handleResetToDefaults = async () => {
    if (!confirm("Are you sure you want to reset to default bloatware list? This will remove all custom packages.")) {
      return
    }

    try {
      const result = await resetBloatwareList()
      toast({
        title: "Success",
        description: result.message
      })
      await loadBloatwarePackages()
    } catch (error: any) {
      toast({
        title: "Error",
        description: error.message || "Failed to reset bloatware list",
        variant: "destructive"
      })
    }
  }

  return (
    <div className="min-h-screen">
      <Header
        isDark={isDark}
        onToggleDark={toggleTheme}
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
          <div className="mb-6 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="rounded-lg bg-red-500/10 p-2">
                <Package className="h-5 w-5 text-red-600 dark:text-red-500" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-card-foreground">Bloatware Management</h2>
                <p className="text-xs text-muted-foreground">
                  {isLoadingBloatware ? "Loading..." : `${bloatwarePackages.length} packages`}
                </p>
              </div>
            </div>
            <Button 
              onClick={handleResetToDefaults}
              variant="outline"
              size="sm"
              className="gap-2"
            >
              <RotateCcw className="h-4 w-4" />
              Reset to Defaults
            </Button>
          </div>
          
          <p className="mb-6 text-sm text-muted-foreground">
            Manage the global list of bloatware packages that will be automatically disabled during device enrollment. 
            This list applies to all new device enrollments.
          </p>

          {/* Add Package Input */}
          <div className="mb-6 flex gap-2">
            <Input
              value={newPackageName}
              onChange={(e) => setNewPackageName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleAddPackage()}
              placeholder="com.example.bloatware"
              className="font-mono text-sm"
              disabled={isAddingPackage}
            />
            <Button 
              onClick={handleAddPackage}
              disabled={isAddingPackage || !newPackageName.trim()}
              className="gap-2 whitespace-nowrap"
            >
              {isAddingPackage ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Plus className="h-4 w-4" />
              )}
              Add Package
            </Button>
          </div>

          {/* Package List */}
          <div className="rounded-lg border border-border">
            {isLoadingBloatware ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : bloatwarePackages.length === 0 ? (
              <div className="py-12 text-center text-sm text-muted-foreground">
                No packages configured. Add packages above to get started.
              </div>
            ) : (
              <div className="max-h-[400px] overflow-y-auto">
                <table className="w-full">
                  <thead className="sticky top-0 border-b border-border bg-muted/50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground">Package Name</th>
                      <th className="w-20 px-4 py-3 text-right text-xs font-semibold text-muted-foreground">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {bloatwarePackages.map((pkg) => (
                      <tr key={pkg.id} className="border-b border-border last:border-0 hover:bg-muted/30">
                        <td className="px-4 py-3 font-mono text-xs text-card-foreground">{pkg.package_name}</td>
                        <td className="px-4 py-3 text-right">
                          <Button
                            onClick={() => handleDeletePackage(pkg.package_name)}
                            variant="ghost"
                            size="sm"
                            className="h-8 w-8 p-0 text-red-600 hover:bg-red-500/10 hover:text-red-700 dark:text-red-500 dark:hover:text-red-400"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </Card>
      </main>
    </div>
  )
}
