"use client"
import { ProtectedLayout } from "@/components/protected-layout"

import { useState, useEffect } from "react"
import { Plus, Trash2, Send, Settings, Battery, Shield } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Header } from "@/components/header"
import { Sidebar } from "@/components/sidebar"
import { toast } from "sonner"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
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
  const [isDark, setIsDark] = useState(false)
  const [isSidebarOpen, setIsSidebarOpen] = useState(true)
  const [lastUpdated, setLastUpdated] = useState(Date.now())
  const [whitelist, setWhitelist] = useState<WhitelistEntry[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false)
  const [packageName, setPackageName] = useState("")
  const [appName, setAppName] = useState("")
  const [isApplying, setIsApplying] = useState(false)

  useEffect(() => {
    const isDarkMode = localStorage.getItem('darkMode') === 'true'
    setIsDark(isDarkMode)
  }, [])

  useEffect(() => {
    const sidebarOpen = localStorage.getItem('sidebarOpen')
    if (sidebarOpen !== null) {
      setIsSidebarOpen(sidebarOpen === 'true')
    }
  }, [])

  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add("dark")
    } else {
      document.documentElement.classList.remove("dark")
    }
  }, [isDark])

  useEffect(() => {
    loadWhitelist()
  }, [])

  const loadWhitelist = async () => {
    try {
      const token = localStorage.getItem('access_token')
      const response = await fetch('/v1/battery-whitelist', {
        headers: {
          'Authorization': `Bearer ${token}`,
        }
      })
      
      if (response.ok) {
        const data = await response.json()
        setWhitelist(data)
        setLastUpdated(Date.now())
      } else {
        toast.error('Failed to load battery whitelist')
      }
    } catch (error) {
      console.error('Failed to load whitelist:', error)
      toast.error('Failed to load battery whitelist')
    } finally {
      setIsLoading(false)
    }
  }

  const handleToggleDark = () => {
    const newIsDark = !isDark
    setIsDark(newIsDark)
    localStorage.setItem('darkMode', String(newIsDark))
  }

  const handleToggleSidebar = () => {
    const newState = !isSidebarOpen
    setIsSidebarOpen(newState)
    localStorage.setItem('sidebarOpen', newState.toString())
  }

  const handleAddToWhitelist = async () => {
    if (!packageName.trim() || !appName.trim()) {
      toast.error('Package name and app name are required')
      return
    }

    try {
      const token = localStorage.getItem('access_token')
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
        loadWhitelist()
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
      const token = localStorage.getItem('access_token')
      const response = await fetch(`/v1/battery-whitelist/${id}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
        }
      })

      if (response.ok) {
        toast.success(`Removed ${appName} from whitelist`)
        loadWhitelist()
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
      const token = localStorage.getItem('access_token')
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

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
        <Sidebar isOpen={isSidebarOpen} onToggle={handleToggleSidebar} />
        
        <Header
          lastUpdated={lastUpdated}
          alertCount={0}
          isDark={isDark}
          onToggleDark={handleToggleDark}
          onOpenSettings={() => {}}
          onRefresh={loadWhitelist}
          onToggleSidebar={handleToggleSidebar}
        />
        <div className="flex items-center justify-center h-[calc(100vh-64px)]">
          <div className="text-gray-500 dark:text-gray-400">Loading...</div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
      <Sidebar isOpen={isSidebarOpen} onToggle={handleToggleSidebar} />
      
      <Header
        lastUpdated={lastUpdated}
        alertCount={0}
        isDark={isDark}
        onToggleDark={handleToggleDark}
        onOpenSettings={() => {}}
        onRefresh={loadWhitelist}
        onToggleSidebar={handleToggleSidebar}
      />
      
      <main className={`transition-all duration-300 container mx-auto px-4 pt-24 pb-8 max-w-7xl ${isSidebarOpen ? 'lg:ml-64' : 'lg:ml-16'}`}>
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
    </div>
  )
}
