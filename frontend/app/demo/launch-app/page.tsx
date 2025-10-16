"use client"

import { useState, useEffect } from "react"
import { Rocket, Search } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Checkbox } from "@/components/ui/checkbox"
import { Header } from "@/components/header"
import { Sidebar } from "@/components/sidebar"
import { SettingsDrawer } from "@/components/settings-drawer"
import { DemoApiService } from "@/lib/demoApiService"
import { toast } from "sonner"

interface Device {
  id: string
  alias: string
  status: string
  last_seen: string
  app_version: string
}

export default function DemoLaunchAppPage() {
  const [isDark, setIsDark] = useState(false)
  const [isSidebarOpen, setIsSidebarOpen] = useState(true)
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  const [lastUpdated] = useState(Date.now())
  const [devices, setDevices] = useState<Device[]>([])
  const [selectedDevices, setSelectedDevices] = useState<Set<string>>(new Set())
  const [packageName, setPackageName] = useState("com.speedtest.androidspeedtest")
  const [searchQuery, setSearchQuery] = useState("")
  const [isLaunching, setIsLaunching] = useState(false)

  useEffect(() => {
    const isDarkMode = localStorage.getItem('darkMode') === 'true'
    setIsDark(isDarkMode)
    if (isDarkMode) {
      document.documentElement.classList.add("dark")
    } else {
      document.documentElement.classList.remove("dark")
    }
    loadDevices()
  }, [])

  const loadDevices = async () => {
    try {
      const response = await DemoApiService.fetch('/v1/devices')
      const data = await response.json()
      setDevices(data.devices || [])
    } catch (error) {
      console.error('Failed to load devices:', error)
    }
  }

  const handleToggleDark = () => {
    const newDark = !isDark
    setIsDark(newDark)
    localStorage.setItem('darkMode', newDark.toString())
  }

  const handleToggleSidebar = () => {
    setIsSidebarOpen(!isSidebarOpen)
  }

  const handleDeviceToggle = (deviceId: string) => {
    const newSelected = new Set(selectedDevices)
    if (newSelected.has(deviceId)) {
      newSelected.delete(deviceId)
    } else {
      newSelected.add(deviceId)
    }
    setSelectedDevices(newSelected)
  }

  const handleSelectAll = () => {
    if (selectedDevices.size === onlineDevices.length) {
      setSelectedDevices(new Set())
    } else {
      setSelectedDevices(new Set(onlineDevices.map(d => d.id)))
    }
  }

  const handleLaunchApp = async () => {
    if (selectedDevices.size === 0) {
      toast.error('Please select at least one device')
      return
    }

    if (!packageName.trim()) {
      toast.error('Please enter a package name')
      return
    }

    setIsLaunching(true)
    try {
      const response = await DemoApiService.fetch('/v1/remote/launch-app', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_ids: Array.from(selectedDevices),
          package_name: packageName
        })
      })
      const data = await response.json()
      toast.success(`Launch command sent to ${selectedDevices.size} device(s) (demo mode)`)
      setSelectedDevices(new Set())
    } catch (error) {
      toast.error('Failed to send launch command')
    } finally {
      setIsLaunching(false)
    }
  }

  const onlineDevices = devices.filter(d => d.status === 'online')
  const filteredDevices = onlineDevices.filter(d => 
    d.alias.toLowerCase().includes(searchQuery.toLowerCase()) ||
    d.id.toLowerCase().includes(searchQuery.toLowerCase())
  )

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

      <main className={`transition-all duration-300 mx-auto max-w-[1280px] px-6 pb-12 pt-20 md:px-8 ${isSidebarOpen ? 'lg:ml-64' : 'lg:ml-16'}`}>
        <div className="space-y-6">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">Launch App</h2>
            <p className="mt-1 text-sm text-muted-foreground">Remotely launch applications on selected devices</p>
          </div>

          <div className="grid gap-6 md:grid-cols-2">
            <div className="rounded-lg border border-border/40 bg-card p-6 space-y-4">
              <div className="space-y-2">
                <Label htmlFor="package-name">Package Name</Label>
                <Input
                  id="package-name"
                  type="text"
                  value={packageName}
                  onChange={(e) => setPackageName(e.target.value)}
                  placeholder="com.example.app"
                />
                <p className="text-xs text-muted-foreground">
                  Enter the Android package name of the app to launch
                </p>
              </div>

              <div className="rounded-lg bg-muted p-3 space-y-2">
                <p className="text-sm font-medium">Common Apps:</p>
                <div className="flex flex-wrap gap-2">
                  <Button 
                    size="sm" 
                    variant="outline" 
                    onClick={() => setPackageName('com.speedtest.androidspeedtest')}
                  >
                    Speedtest
                  </Button>
                  <Button 
                    size="sm" 
                    variant="outline" 
                    onClick={() => setPackageName('com.google.android.gm')}
                  >
                    Gmail
                  </Button>
                  <Button 
                    size="sm" 
                    variant="outline" 
                    onClick={() => setPackageName('com.android.chrome')}
                  >
                    Chrome
                  </Button>
                </div>
              </div>

              <Button 
                onClick={handleLaunchApp} 
                disabled={isLaunching || selectedDevices.size === 0}
                className="w-full gap-2"
              >
                <Rocket className="h-4 w-4" />
                {isLaunching ? 'Launching...' : `Launch on ${selectedDevices.size} Device(s)`}
              </Button>
            </div>

            <div className="rounded-lg border border-border/40 bg-card p-6 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-medium">Select Devices ({selectedDevices.size})</h3>
                <Button size="sm" variant="outline" onClick={handleSelectAll}>
                  {selectedDevices.size === onlineDevices.length ? 'Deselect All' : 'Select All'}
                </Button>
              </div>

              <div className="relative">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  type="text"
                  placeholder="Search devices..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-9"
                />
              </div>

              <div className="max-h-[400px] overflow-y-auto space-y-2">
                {filteredDevices.length === 0 ? (
                  <p className="text-sm text-muted-foreground text-center py-4">No online devices found</p>
                ) : (
                  filteredDevices.map((device) => (
                    <div
                      key={device.id}
                      className="flex items-center space-x-3 rounded-lg border border-border/40 p-3 hover:bg-muted/50 transition-colors"
                    >
                      <Checkbox
                        id={device.id}
                        checked={selectedDevices.has(device.id)}
                        onCheckedChange={() => handleDeviceToggle(device.id)}
                      />
                      <label htmlFor={device.id} className="flex-1 cursor-pointer">
                        <div className="font-medium">{device.alias}</div>
                        <div className="text-xs text-muted-foreground">{device.id}</div>
                      </label>
                      <div className="text-xs px-2 py-1 rounded-full bg-green-500/10 text-green-600 dark:text-green-400">
                        {device.status}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
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
