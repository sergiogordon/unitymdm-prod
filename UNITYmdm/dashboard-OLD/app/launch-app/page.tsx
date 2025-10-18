"use client"
import { ProtectedLayout } from "@/components/protected-layout"

import { useState, useEffect } from "react"
import { Send, Loader2, Smartphone, CheckCircle2, XCircle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Checkbox } from "@/components/ui/checkbox"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Header } from "@/components/header"
import { Sidebar } from "@/components/sidebar"
import { toast } from "sonner"

interface Device {
  id: string
  alias: string
  status: string
  model?: string
}

interface LaunchResult {
  device_id: string
  alias: string
  ok: boolean
  message?: string
  error?: string
}

export default function LaunchAppPage() {
  return (
    <ProtectedLayout>
      <LaunchAppContent />
    </ProtectedLayout>
  )
}

function LaunchAppContent() {
  const [devices, setDevices] = useState<Device[]>([])
  const [selectedDeviceIds, setSelectedDeviceIds] = useState<Set<string>>(new Set())
  const [packageName, setPackageName] = useState("")
  const [intentUri, setIntentUri] = useState("")
  const [isLoading, setIsLoading] = useState(true)
  const [isLaunching, setIsLaunching] = useState(false)
  const [launchResults, setLaunchResults] = useState<LaunchResult[]>([])
  const [isDark, setIsDark] = useState(false)
  const [isSidebarOpen, setIsSidebarOpen] = useState(true)

  useEffect(() => {
    loadDevices()
  }, [])

  useEffect(() => {
    const isDarkMode = localStorage.getItem('darkMode') === 'true'
    setIsDark(isDarkMode)
    if (isDarkMode) {
      document.documentElement.classList.add("dark")
    } else {
      document.documentElement.classList.remove("dark")
    }
  }, [])

  useEffect(() => {
    const sidebarOpen = localStorage.getItem('sidebarOpen')
    if (sidebarOpen !== null) {
      setIsSidebarOpen(sidebarOpen === 'true')
    }
  }, [])

  const handleToggleDark = () => {
    const newDark = !isDark
    setIsDark(newDark)
    if (newDark) {
      document.documentElement.classList.add("dark")
    } else {
      document.documentElement.classList.remove("dark")
    }
    localStorage.setItem('darkMode', newDark.toString())
  }

  const handleToggleSidebar = () => {
    const newState = !isSidebarOpen
    setIsSidebarOpen(newState)
    localStorage.setItem('sidebarOpen', newState.toString())
  }

  const loadDevices = async () => {
    try {
      const token = localStorage.getItem('access_token')
      const headers: HeadersInit = {}
      if (token) {
        headers['Authorization'] = `Bearer ${token}`
      }
      
      const response = await fetch("/v1/devices?page=1&limit=1000", { headers })
      if (response.ok) {
        const data = await response.json()
        setDevices(data.devices || [])
      }
    } catch (error) {
      console.error("Failed to load devices:", error)
      toast.error("Failed to load devices")
    } finally {
      setIsLoading(false)
    }
  }

  const toggleDevice = (deviceId: string) => {
    const newSelected = new Set(selectedDeviceIds)
    if (newSelected.has(deviceId)) {
      newSelected.delete(deviceId)
    } else {
      newSelected.add(deviceId)
    }
    setSelectedDeviceIds(newSelected)
  }

  const selectAll = () => {
    const onlineDevices = devices.filter(d => d.status === "online")
    setSelectedDeviceIds(new Set(onlineDevices.map(d => d.id)))
  }

  const deselectAll = () => {
    setSelectedDeviceIds(new Set())
  }

  const launchUnity = () => {
    setPackageName("com.android.unity")
    setIntentUri("")
    toast.info("Unity configured - click Launch to open it on selected devices")
  }

  const handleLaunch = async () => {
    if (selectedDeviceIds.size === 0) {
      toast.error("Please select at least one device")
      return
    }

    if (!packageName.trim()) {
      toast.error("Please enter a package name")
      return
    }

    setIsLaunching(true)
    setLaunchResults([])

    try {
      const body: any = {
        device_ids: Array.from(selectedDeviceIds),
        package_name: packageName.trim()
      }
      
      // Add intent URI if provided
      if (intentUri.trim()) {
        body.intent_uri = intentUri.trim()
      }

      const token = localStorage.getItem('access_token')
      const headers: HeadersInit = { "Content-Type": "application/json" }
      if (token) {
        headers['Authorization'] = `Bearer ${token}`
      }
      
      const response = await fetch("/v1/remote/launch-app", {
        method: "POST",
        headers,
        body: JSON.stringify(body)
      })

      const data = await response.json()

      if (response.ok) {
        setLaunchResults(data.results || [])
        
        if (data.success_count === data.total) {
          toast.success(`App launched on all ${data.total} device(s)`)
        } else {
          toast.warning(`Launched on ${data.success_count}/${data.total} devices`)
        }
      } else {
        toast.error(data.detail || "Failed to launch app")
      }
    } catch (error) {
      console.error("Failed to launch app:", error)
      toast.error("Failed to launch app")
    } finally {
      setIsLaunching(false)
    }
  }

  const onlineDevices = devices.filter(d => d.status === "online")
  const offlineDevices = devices.filter(d => d.status !== "online")

  return (
    <div className="min-h-screen">
      <Sidebar isOpen={isSidebarOpen} onToggle={handleToggleSidebar} />
      
      <Header
        lastUpdated={Date.now()}
        alertCount={0}
        isDark={isDark}
        onToggleDark={handleToggleDark}
        onOpenSettings={() => {}}
        onRefresh={loadDevices}
        onToggleSidebar={handleToggleSidebar}
      />

      <main className={`transition-all duration-300 mx-auto max-w-[1280px] px-6 pb-12 pt-20 md:px-8 ${isSidebarOpen ? 'lg:ml-64' : 'lg:ml-16'}`}>
        <div className="space-y-6">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Launch App</h1>
            <p className="text-muted-foreground mt-2">
              Launch a specific app on one or more devices remotely
            </p>
          </div>

      <div className="grid gap-6 md:grid-cols-2">
        {/* Left: App Config */}
        <Card>
          <CardHeader>
            <CardTitle>App Configuration</CardTitle>
            <CardDescription>
              Enter the package name of the app to launch
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-4">
              <div>
                <p className="text-sm font-medium mb-2">Quick Actions</p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={launchUnity}
                  disabled={isLaunching}
                  className="w-full"
                >
                  🎮 Launch Unity
                </Button>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">Package Name</label>
                <Input
                  placeholder="com.example.app"
                  value={packageName}
                  onChange={(e) => setPackageName(e.target.value)}
                  disabled={isLaunching}
                />
                <p className="text-xs text-muted-foreground">
                  Common examples: com.android.unity, com.android.chrome
                </p>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">Intent URI (Optional)</label>
                <Input
                  placeholder="intent://scan/#Intent;scheme=zxing;end"
                  value={intentUri}
                  onChange={(e) => setIntentUri(e.target.value)}
                  disabled={isLaunching}
                />
                <p className="text-xs text-muted-foreground">
                  Deep link URI for apps that support it (advanced)
                </p>
              </div>
            </div>

            <Button
              onClick={handleLaunch}
              disabled={selectedDeviceIds.size === 0 || !packageName.trim() || isLaunching}
              className="w-full"
            >
              {isLaunching ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Launching...
                </>
              ) : (
                <>
                  <Send className="mr-2 h-4 w-4" />
                  Launch on {selectedDeviceIds.size} Device{selectedDeviceIds.size !== 1 ? 's' : ''}
                </>
              )}
            </Button>

            {launchResults.length > 0 && (
              <div className="mt-4 space-y-2">
                <p className="text-sm font-medium">Results:</p>
                <div className="space-y-1">
                  {launchResults.map((result) => (
                    <div key={result.device_id} className="flex items-center gap-2 text-sm">
                      {result.ok ? (
                        <CheckCircle2 className="h-4 w-4 text-green-500" />
                      ) : (
                        <XCircle className="h-4 w-4 text-red-500" />
                      )}
                      <span className="flex-1">
                        {result.alias || result.device_id}
                      </span>
                      {result.error && (
                        <span className="text-xs text-muted-foreground">{result.error}</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Right: Device Selection */}
        <Card>
          <CardHeader>
            <CardTitle>Device Selection</CardTitle>
            <CardDescription>
              Select devices to launch the app on
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={selectAll}
                    disabled={onlineDevices.length === 0}
                  >
                    Select All Online
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={deselectAll}
                    disabled={selectedDeviceIds.size === 0}
                  >
                    Deselect All
                  </Button>
                </div>

                <div className="space-y-2">
                  {onlineDevices.length > 0 && (
                    <div className="space-y-2">
                      <p className="text-sm font-medium text-green-600">Online ({onlineDevices.length})</p>
                      {onlineDevices.map((device) => (
                        <div
                          key={device.id}
                          className="flex items-center gap-3 p-2 rounded-md hover:bg-muted"
                        >
                          <Checkbox
                            checked={selectedDeviceIds.has(device.id)}
                            onCheckedChange={() => toggleDevice(device.id)}
                          />
                          <Smartphone className="h-4 w-4 text-muted-foreground" />
                          <div 
                            className="flex-1 min-w-0 cursor-pointer"
                            onClick={() => toggleDevice(device.id)}
                          >
                            <p className="text-sm font-medium truncate">{device.alias}</p>
                            {device.model && (
                              <p className="text-xs text-muted-foreground truncate">{device.model}</p>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {offlineDevices.length > 0 && (
                    <div className="space-y-2 mt-4">
                      <p className="text-sm font-medium text-muted-foreground">Offline ({offlineDevices.length})</p>
                      {offlineDevices.map((device) => (
                        <div
                          key={device.id}
                          className="flex items-center gap-3 p-2 rounded-md opacity-50"
                        >
                          <Checkbox disabled />
                          <Smartphone className="h-4 w-4 text-muted-foreground" />
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium truncate">{device.alias}</p>
                            {device.model && (
                              <p className="text-xs text-muted-foreground truncate">{device.model}</p>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {devices.length === 0 && (
                    <p className="text-sm text-muted-foreground text-center py-4">
                      No devices found
                    </p>
                  )}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
        </div>
      </main>
    </div>
  )
}
