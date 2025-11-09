"use client"
import { ProtectedLayout } from "@/components/protected-layout"

import { useState, useEffect } from "react"
import {
  Plus,
  Trash2,
  Send,
  Settings,
  Battery,
  Shield,
  PackageMinus,
  PackagePlus,
  Loader2,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { toast } from "sonner"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

interface WhitelistEntry {
  id: number
  package_name: string
  app_name: string
  added_at: string
  enabled: boolean
  added_by: string
}

interface BloatwarePackage {
  id: number
  package_name: string
  enabled: boolean
  description?: string | null
}

const ADB_MODIFICATIONS = [
  { category: "Battery Optimizations", items: [
    "Disable Adaptive Battery (adaptive_battery_management_enabled = 0)",
    "Disable App Standby (app_standby_enabled = 0)",
    "Disable App Restrictions (app_restriction_enabled = false)",
    "Disable Dynamic Power Savings (dynamic_power_savings_enabled = 0)",
  ]},
  { category: "Performance", items: [
    "Reduce animation scale to 0.5x (window/transition/animator_duration_scale)",
    "Enable ambient tilt and touch to wake",
  ]},
  { category: "Disabled Apps", items: [
    "Verizon bloatware (MyVerizon, APN Library, MIPS Services, etc.)",
    "Pre-installed games (Candy Crush, Toon Blast, Sudoku, etc.)",
    "YouTube Music",
  ]},
  { category: "Security", items: [
    "Enable installation from unknown sources",
    "Enabled Verizon device management (dmclientupdate, obdm)",
  ]},
]

export default function DeviceOptimizationPage() {
  return (
    <ProtectedLayout>
      <DeviceOptimizationContent />
    </ProtectedLayout>
  )
}

function DeviceOptimizationContent() {
  const [whitelist, setWhitelist] = useState<WhitelistEntry[]>([])
  const [bloatwarePackages, setBloatwarePackages] = useState<BloatwarePackage[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false)
  const [packageName, setPackageName] = useState("")
  const [appName, setAppName] = useState("")
  const [isApplying, setIsApplying] = useState(false)
  const [isBloatDialogOpen, setIsBloatDialogOpen] = useState(false)
  const [bloatwareInput, setBloatwareInput] = useState("")
  const [isUpdatingBloatware, setIsUpdatingBloatware] = useState(false)

  useEffect(() => {
    loadAllData()
  }, [])

  const loadAllData = async () => {
    setIsLoading(true)
    await Promise.all([loadWhitelist(), loadBloatwarePackages()])
    setIsLoading(false)
  }

  const loadWhitelist = async () => {
    try {
      const token = localStorage.getItem('auth_token')
      const response = await fetch('/v1/battery-whitelist', {
        headers: {
          'Authorization': `Bearer ${token}`,
        }
      })
      
      if (response.ok) {
        const data = await response.json()
        setWhitelist(data)
      } else {
        toast.error('Failed to load battery whitelist')
      }
    } catch (error) {
      console.error('Failed to load whitelist:', error)
      toast.error('Failed to load battery whitelist')
    }
  }

  const loadBloatwarePackages = async () => {
    try {
      const token = localStorage.getItem('auth_token')
      const response = await fetch('/admin/bloatware-list/json', {
        headers: {
          'Authorization': `Bearer ${token}`,
        }
      })

      if (response.ok) {
        const data = await response.json()
        setBloatwarePackages(data.packages ?? [])
      } else {
        toast.error('Failed to load disabled apps list')
      }
    } catch (error) {
      console.error('Failed to load bloatware list:', error)
      toast.error('Failed to load disabled apps list')
    }
  }

  const handleAddToWhitelist = async () => {
    if (!packageName.trim() || !appName.trim()) {
      toast.error('Package name and app name are required')
      return
    }

    try {
      const token = localStorage.getItem('auth_token')
      const response = await fetch('/v1/battery-whitelist', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          package_name: packageName.trim(),
          app_name: appName.trim(),
        })
      })

      if (response.ok) {
        toast.success(`Added ${appName} to battery whitelist`)
        setIsAddDialogOpen(false)
        setPackageName("")
        setAppName("")
        await loadWhitelist()
      } else {
        const error = await response.json()
        toast.error(error.detail || 'Failed to add to whitelist')
      }
    } catch (error) {
      console.error('Failed to add to whitelist:', error)
      toast.error('Failed to add to whitelist')
    }
  }

  const handleRemoveFromWhitelist = async (id: number, appName: string) => {
    if (!confirm(`Remove ${appName} from battery whitelist?`)) {
      return
    }

    try {
      const token = localStorage.getItem('auth_token')
      const response = await fetch(`/v1/battery-whitelist/${id}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
        }
      })

      if (response.ok) {
        toast.success(`Removed ${appName} from whitelist`)
        await loadWhitelist()
      } else {
        toast.error('Failed to remove from whitelist')
      }
    } catch (error) {
      console.error('Failed to remove from whitelist:', error)
      toast.error('Failed to remove from whitelist')
    }
  }

  const handleApplyToFleet = async () => {
    if (!confirm('Apply battery whitelist to all online devices? This will send FCM notifications to exempt whitelisted apps from battery optimization.')) {
      return
    }

    setIsApplying(true)
    try {
      const token = localStorage.getItem('auth_token')
      const response = await fetch('/v1/devices/apply-battery-whitelist', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(null)
      })

      if (response.ok) {
        const result = await response.json()
        toast.success(`Applied to ${result.success_count}/${result.total_devices} devices`)
      } else {
        const error = await response.json()
        toast.error(error.detail || 'Failed to apply whitelist')
      }
    } catch (error) {
      console.error('Failed to apply whitelist:', error)
      toast.error('Failed to apply whitelist')
    } finally {
      setIsApplying(false)
    }
  }

  const handleAddBloatwarePackages = async () => {
    const parsedPackages = Array.from(
      new Set(
        bloatwareInput
          .split(/[\n,]+/)
          .map((pkg) => pkg.trim())
          .filter((pkg) => pkg.length > 0)
      )
    )

    if (parsedPackages.length === 0) {
      toast.error('Enter at least one package name (one per line or separated by commas)')
      return
    }

    const packageRegex = /^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$/
    const invalidPackages = parsedPackages.filter((pkg) => !packageRegex.test(pkg))

    if (invalidPackages.length > 0) {
      toast.error(`Invalid package name(s): ${invalidPackages.join(', ')}`)
      return
    }

    const existingNames = new Set(bloatwarePackages.map((pkg) => pkg.package_name))
    const newPackages = parsedPackages.filter((pkg) => !existingNames.has(pkg))

    if (newPackages.length === 0) {
      toast.info('All packages already exist in the disabled list')
      return
    }

    setIsUpdatingBloatware(true)

    try {
      const token = localStorage.getItem('auth_token')
      const added: string[] = []
      const skipped: string[] = []

      for (const pkg of newPackages) {
        const response = await fetch('/admin/bloatware-list/add', {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ package_name: pkg }),
        })

        if (response.ok) {
          added.push(pkg)
        } else {
          const error = await response.json().catch(() => ({}))
          skipped.push(error.detail ?? pkg)
        }
      }

      if (added.length > 0) {
        toast.success(`Added ${added.length} package${added.length === 1 ? '' : 's'} to disabled list`)
      }

      if (skipped.length > 0) {
        toast.error(`Skipped: ${skipped.join(', ')}`)
      }

      await loadBloatwarePackages()
      setIsBloatDialogOpen(false)
      setBloatwareInput("")
    } catch (error) {
      console.error('Failed to add disabled apps:', error)
      toast.error('Failed to add disabled apps')
    } finally {
      setIsUpdatingBloatware(false)
    }
  }

  const handleRemoveBloatwarePackage = async (packageName: string) => {
    if (!confirm(`Remove ${packageName} from the disabled apps list?`)) {
      return
    }

    try {
      const token = localStorage.getItem('auth_token')
      const response = await fetch(`/admin/bloatware-list/${encodeURIComponent(packageName)}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })

      if (response.ok) {
        toast.success(`Removed ${packageName}`)
        await loadBloatwarePackages()
      } else {
        const error = await response.json().catch(() => ({}))
        toast.error(error.detail || 'Failed to remove package')
      }
    } catch (error) {
      console.error('Failed to remove disabled app:', error)
      toast.error('Failed to remove package')
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading…
        </div>
      </div>
    )
  }

  return (
    <>
      <main className="container mx-auto px-4 py-8 max-w-7xl">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-semibold text-gray-900 dark:text-white mb-2">
              Device Optimization
            </h1>
            <p className="text-gray-600 dark:text-gray-400">
              Manage battery optimization settings and ADB modifications
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
          <Card className="border-gray-200 dark:border-gray-800">
            <CardHeader>
              <div className="flex items-center gap-2">
                <Settings className="h-5 w-5 text-gray-600 dark:text-gray-400" />
                <CardTitle>ADB Script Modifications</CardTitle>
              </div>
              <CardDescription>
                These optimizations are automatically applied during device enrollment via ADB
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {ADB_MODIFICATIONS.map((section, idx) => (
                  <div key={idx} className="border-b border-gray-200 dark:border-gray-800 last:border-0 pb-4 last:pb-0">
                    <h3 className="font-medium text-gray-900 dark:text-white mb-2">{section.category}</h3>
                    <ul className="space-y-1">
                      {section.items.map((item, itemIdx) => (
                        <li key={itemIdx} className="text-sm text-gray-600 dark:text-gray-400 flex items-start gap-2">
                          <span className="text-green-500 mt-1">✓</span>
                          <span>{item}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card className="border-gray-200 dark:border-gray-800">
            <CardHeader>
              <div className="flex items-center gap-2">
                <PackageMinus className="h-5 w-5 text-red-600 dark:text-red-400" />
                <CardTitle>Disabled Apps (Bloatware)</CardTitle>
              </div>
              <CardDescription>
                Packages that ADB enrollment scripts disable during provisioning
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="flex flex-wrap gap-2">
                  <Button
                    onClick={() => setIsBloatDialogOpen(true)}
                    size="sm"
                    className="flex items-center gap-2"
                  >
                    <PackagePlus className="h-4 w-4" />
                    Add Packages
                  </Button>
                </div>

                {bloatwarePackages.length === 0 ? (
                  <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                    No packages in the disabled list. Add package names to disable unwanted apps during enrollment.
                  </div>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Package Name</TableHead>
                        <TableHead className="text-right">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {bloatwarePackages.map((pkg) => (
                        <TableRow key={pkg.id}>
                          <TableCell className="font-mono text-sm text-gray-700 dark:text-gray-300">
                            {pkg.package_name}
                          </TableCell>
                          <TableCell className="text-right">
                            <Button
                              onClick={() => handleRemoveBloatwarePackage(pkg.package_name)}
                              size="sm"
                              variant="ghost"
                              className="text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-950"
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </div>
            </CardContent>
          </Card>

          <Card className="border-gray-200 dark:border-gray-800">
            <CardHeader>
              <div className="flex items-center gap-2">
                <Battery className="h-5 w-5 text-green-600 dark:text-green-400" />
                <CardTitle>Battery Optimization Whitelist</CardTitle>
              </div>
              <CardDescription>
                Apps exempt from Android's battery optimization and Doze mode
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="flex gap-2">
                  <Button
                    onClick={() => setIsAddDialogOpen(true)}
                    size="sm"
                    className="flex items-center gap-2"
                  >
                    <Plus className="h-4 w-4" />
                    Add App
                  </Button>
                  <Button
                    onClick={handleApplyToFleet}
                    disabled={isApplying || whitelist.length === 0}
                    size="sm"
                    variant="outline"
                    className="flex items-center gap-2"
                  >
                    <Send className="h-4 w-4" />
                    {isApplying ? 'Applying...' : 'Apply to Fleet'}
                  </Button>
                </div>

                {whitelist.length === 0 ? (
                  <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                    No apps in whitelist. Add apps to prevent battery optimization.
                  </div>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>App Name</TableHead>
                        <TableHead>Package Name</TableHead>
                        <TableHead className="text-right">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {whitelist.map((entry) => (
                        <TableRow key={entry.id}>
                          <TableCell className="font-medium">{entry.app_name}</TableCell>
                          <TableCell className="font-mono text-sm text-gray-600 dark:text-gray-400">
                            {entry.package_name}
                          </TableCell>
                          <TableCell className="text-right">
                            <Button
                              onClick={() => handleRemoveFromWhitelist(entry.id, entry.app_name)}
                              size="sm"
                              variant="ghost"
                              className="text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-950"
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </div>
            </CardContent>
          </Card>
        </div>

        <Card className="border-gray-200 dark:border-gray-800">
          <CardHeader>
            <div className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-blue-600 dark:text-blue-400" />
              <CardTitle>How It Works</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <h3 className="font-medium text-gray-900 dark:text-white mb-2">For New Devices (ADB Enrollment)</h3>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                When you generate an ADB script, all whitelisted apps are automatically included in the setup commands.
                The script will disable Adaptive Battery globally and whitelist each app from Doze mode and background restrictions.
              </p>
            </div>
            <div>
              <h3 className="font-medium text-gray-900 dark:text-white mb-2">For Existing Devices (FCM Push)</h3>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Click "Apply to Fleet" to send FCM notifications to all online devices. Each device will receive the whitelist
                and request battery optimization exemption for all listed apps. Devices must be online and have FCM configured.
              </p>
            </div>
            <div>
              <h3 className="font-medium text-gray-900 dark:text-white mb-2">Android App Integration</h3>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                The NexMDM Android app automatically fetches the whitelist from the server on startup and applies battery
                optimization exemptions for itself and all whitelisted apps. This ensures persistent protection across reboots.
              </p>
            </div>
          </CardContent>
        </Card>
      </main>

      <Dialog open={isAddDialogOpen} onOpenChange={setIsAddDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add App to Battery Whitelist</DialogTitle>
            <DialogDescription>
              Add an app package to exempt from battery optimization and Doze mode
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="appName">App Name</Label>
              <Input
                id="appName"
                placeholder="e.g., Speedtest by Ookla"
                value={appName}
                onChange={(e) => setAppName(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="packageName">Package Name</Label>
              <Input
                id="packageName"
                placeholder="e.g., com.speedtest.androidspeedtest"
                value={packageName}
                onChange={(e) => setPackageName(e.target.value)}
                className="font-mono text-sm"
              />
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Find package names using: adb shell pm list packages | grep appname
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsAddDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleAddToWhitelist}>
              Add to Whitelist
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={isBloatDialogOpen} onOpenChange={setIsBloatDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Disabled Apps</DialogTitle>
            <DialogDescription>
              Paste package names (newline or comma separated) to disable during device enrollment.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4 max-h-[60vh] overflow-y-auto pr-1">
            <div className="space-y-2">
              <Label htmlFor="bloatwarePackages">Package Names</Label>
              <Textarea
                id="bloatwarePackages"
                placeholder={`com.example.app.one\ncom.example.app.two`}
                value={bloatwareInput}
                onChange={(e) => setBloatwareInput(e.target.value)}
                className="font-mono text-sm"
                rows={6}
              />
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Use Android package format (e.g., com.company.app). Existing packages are ignored automatically.
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsBloatDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleAddBloatwarePackages} disabled={isUpdatingBloatware}>
              {isUpdatingBloatware ? (
                <span className="flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Adding…
                </span>
              ) : (
                'Add Packages'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
