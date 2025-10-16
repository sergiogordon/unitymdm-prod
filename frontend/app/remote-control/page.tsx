"use client"
import { ProtectedLayout } from "@/components/protected-layout"

import { useState, useEffect, useRef } from "react"
import { Smartphone, Monitor, Keyboard, X, Eye, RotateCcw, Power } from "lucide-react"
import { Header } from "@/components/header"
import { Sidebar } from "@/components/sidebar"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { toast } from "sonner"
import { DeviceScreenViewer } from "@/components/device-screen-viewer"
import { SettingsDrawer } from "@/components/settings-drawer"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"

interface Device {
  id: string
  alias: string
  status: string
  model?: string
  manufacturer?: string
}

export default function RemoteControlPage() {
  return (
    <ProtectedLayout>
      <RemoteControlContent />
    </ProtectedLayout>
  )
}

function RemoteControlContent() {
  const [isDark, setIsDark] = useState(false)
  const [isSidebarOpen, setIsSidebarOpen] = useState(true)
  const [lastUpdated, setLastUpdated] = useState(Date.now())
  const [devices, setDevices] = useState<Device[]>([])
  const [selectedDeviceIds, setSelectedDeviceIds] = useState<Set<string>>(new Set())
  const [isLoading, setIsLoading] = useState(true)
  const [streamingDevices, setStreamingDevices] = useState<Set<string>>(new Set())
  const [textInput, setTextInput] = useState("")
  const [viewingDeviceId, setViewingDeviceId] = useState<string | null>(null)
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  const [showRebootDialog, setShowRebootDialog] = useState(false)
  const [showRestartAppDialog, setShowRestartAppDialog] = useState(false)
  const [isRestarting, setIsRestarting] = useState(false)

  useEffect(() => {
    const darkMode = localStorage.getItem('darkMode') === 'true'
    setIsDark(darkMode)
    if (darkMode) {
      document.documentElement.classList.add('dark')
    }
  }, [])

  useEffect(() => {
    const sidebarOpen = localStorage.getItem('sidebarOpen')
    if (sidebarOpen !== null) {
      setIsSidebarOpen(sidebarOpen === 'true')
    }
  }, [])

  useEffect(() => {
    loadDevices()
  }, [])

  const loadDevices = async () => {
    try {
      // Get JWT token from localStorage
      const token = localStorage.getItem('access_token')
      const headers: HeadersInit = {}
      if (token) {
        headers['Authorization'] = `Bearer ${token}`
      }
      
      const response = await fetch('/v1/devices?page=1&limit=1000', { headers })
      if (response.ok) {
        const data = await response.json()
        setDevices(data.devices || [])
        setLastUpdated(Date.now())
      }
    } catch (error) {
      console.error('Failed to load devices:', error)
      toast.error('Failed to load devices')
    } finally {
      setIsLoading(false)
    }
  }

  const handleToggleDark = () => {
    const newDark = !isDark
    setIsDark(newDark)
    localStorage.setItem('darkMode', newDark.toString())
    if (newDark) {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
  }

  const handleToggleSidebar = () => {
    const newState = !isSidebarOpen
    setIsSidebarOpen(newState)
    localStorage.setItem('sidebarOpen', newState.toString())
  }

  const handleToggleDevice = (deviceId: string) => {
    setSelectedDeviceIds(prev => {
      const newSet = new Set(prev)
      if (newSet.has(deviceId)) {
        newSet.delete(deviceId)
      } else {
        newSet.add(deviceId)
      }
      return newSet
    })
  }

  const handleToggleAll = () => {
    if (selectedDeviceIds.size === devices.length) {
      setSelectedDeviceIds(new Set())
    } else {
      setSelectedDeviceIds(new Set(devices.map(d => d.id)))
    }
  }

  const sendCommand = async (command: string, params: any = {}) => {
    if (selectedDeviceIds.size === 0) {
      toast.error('Please select at least one device')
      return
    }

    try {
      const token = localStorage.getItem('access_token')
      const response = await fetch('/v1/remote/command', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          device_ids: Array.from(selectedDeviceIds),
          command,
          params,
        }),
      })

      const result = await response.json()

      if (response.ok) {
        toast.success(`Command sent to ${result.success_count} device(s)`)
        if (result.failed_count > 0) {
          toast.warning(`${result.failed_count} device(s) failed`)
        }
      } else {
        toast.error('Failed to send command')
      }
    } catch (error) {
      console.error('Failed to send command:', error)
      toast.error('Failed to send command')
    }
  }

  const handleSendText = () => {
    if (!textInput.trim()) {
      toast.error('Please enter text to send')
      return
    }
    sendCommand('text', { text: textInput })
    setTextInput("")
  }

  const handleKey = (key: string) => {
    sendCommand('key', { key })
  }

  const handleReboot = async () => {
    if (selectedDeviceIds.size === 0) {
      toast.error('Please select at least one device')
      return
    }

    setIsRestarting(true)
    setShowRebootDialog(false)

    try {
      const token = localStorage.getItem('access_token')
      const headers: HeadersInit = {
        'Content-Type': 'application/json',
      }
      if (token) {
        headers['Authorization'] = `Bearer ${token}`
      }

      const response = await fetch('/v1/remote/reboot', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          device_ids: Array.from(selectedDeviceIds),
        }),
      })

      const result = await response.json()

      if (response.ok) {
        toast.success(`Reboot command sent to ${result.success_count} device(s)`)
        if (result.failed_count > 0) {
          toast.warning(`${result.failed_count} device(s) failed`)
        }
      } else {
        toast.error('Failed to send reboot command')
      }
    } catch (error) {
      console.error('Failed to reboot devices:', error)
      toast.error('Failed to send reboot command')
    } finally {
      setIsRestarting(false)
    }
  }

  const handleRestartApp = async () => {
    if (selectedDeviceIds.size === 0) {
      toast.error('Please select at least one device')
      return
    }

    setIsRestarting(true)
    setShowRestartAppDialog(false)

    try {
      const token = localStorage.getItem('access_token')
      const headers: HeadersInit = {
        'Content-Type': 'application/json',
      }
      if (token) {
        headers['Authorization'] = `Bearer ${token}`
      }

      const response = await fetch('/v1/remote/restart-app', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          device_ids: Array.from(selectedDeviceIds),
        }),
      })

      const result = await response.json()

      if (response.ok) {
        toast.success(`App restart command sent to ${result.success_count} device(s)`)
        if (result.failed_count > 0) {
          toast.warning(`${result.failed_count} device(s) failed`)
        }
      } else {
        toast.error('Failed to send restart command')
      }
    } catch (error) {
      console.error('Failed to restart app on devices:', error)
      toast.error('Failed to send restart command')
    } finally {
      setIsRestarting(false)
    }
  }

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    )
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
        onRefresh={loadDevices}
        onToggleSidebar={handleToggleSidebar}
      />

      <main className={`transition-all duration-300 mx-auto max-w-[1600px] px-6 pb-12 pt-20 md:px-8 ${isSidebarOpen ? 'lg:ml-64' : 'lg:ml-16'}`}>
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">Remote Control <span className="text-muted-foreground">(Coming Soon)</span></h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Select devices and control them remotely
            </p>
          </div>
          <div className="text-sm text-muted-foreground">
            {selectedDeviceIds.size} of {devices.length} devices selected
          </div>
        </div>

        {devices.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border bg-muted/30 p-12 text-center">
            <Smartphone className="mx-auto h-12 w-12 text-muted-foreground" />
            <h3 className="mt-4 text-lg font-medium">No devices available</h3>
            <p className="mt-2 text-sm text-muted-foreground">
              Enroll devices to start remote control
            </p>
          </div>
        ) : (
          <>
            <div className="mb-6 rounded-lg border border-border bg-card p-4">
              <div className="flex items-center gap-3 mb-4">
                <Checkbox
                  checked={selectedDeviceIds.size === devices.length && devices.length > 0}
                  onCheckedChange={handleToggleAll}
                />
                <span className="text-sm font-medium">Select All Devices</span>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
                {devices.map((device) => (
                  <div
                    key={device.id}
                    className={`rounded-lg border p-3 transition-all ${
                      selectedDeviceIds.has(device.id)
                        ? 'border-primary bg-primary/5'
                        : 'border-border hover:bg-muted/30'
                    }`}
                  >
                    <div className="flex items-start gap-2 cursor-pointer" onClick={() => handleToggleDevice(device.id)}>
                      <Checkbox
                        checked={selectedDeviceIds.has(device.id)}
                        onCheckedChange={() => handleToggleDevice(device.id)}
                        onClick={(e) => e.stopPropagation()}
                      />
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-sm truncate">{device.alias}</div>
                        {device.model && (
                          <div className="text-xs text-muted-foreground truncate">{device.model}</div>
                        )}
                        <div className={`mt-1 text-xs ${
                          device.status === 'online' ? 'text-green-500' : 'text-red-500'
                        }`}>
                          {device.status}
                        </div>
                      </div>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      className="w-full mt-2"
                      onClick={(e) => {
                        e.stopPropagation()
                        setViewingDeviceId(device.id)
                      }}
                      disabled={device.status !== 'online'}
                    >
                      <Eye className="h-3 w-3 mr-1" />
                      View Screen
                    </Button>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-lg border border-border bg-card p-6">
              <h3 className="text-lg font-semibold mb-4">Control Panel</h3>
              
              <div className="space-y-4">
                <div>
                  <label className="text-sm font-medium mb-2 block">Send Text</label>
                  <div className="flex gap-2">
                    <Input
                      placeholder="Enter text to send to devices..."
                      value={textInput}
                      onChange={(e) => setTextInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          handleSendText()
                        }
                      }}
                      disabled={selectedDeviceIds.size === 0}
                    />
                    <Button 
                      onClick={handleSendText}
                      disabled={selectedDeviceIds.size === 0 || !textInput.trim()}
                    >
                      <Keyboard className="h-4 w-4 mr-2" />
                      Send
                    </Button>
                  </div>
                </div>

                <div>
                  <label className="text-sm font-medium mb-2 block">Quick Actions</label>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleKey('HOME')}
                      disabled={selectedDeviceIds.size === 0}
                    >
                      Home
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleKey('BACK')}
                      disabled={selectedDeviceIds.size === 0}
                    >
                      Back
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleKey('RECENT_APPS')}
                      disabled={selectedDeviceIds.size === 0}
                    >
                      Recent Apps
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleKey('POWER')}
                      disabled={selectedDeviceIds.size === 0}
                    >
                      Power/Lock
                    </Button>
                  </div>
                </div>

                <div>
                  <label className="text-sm font-medium mb-2 block">Restart Actions</label>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setShowRestartAppDialog(true)}
                      disabled={selectedDeviceIds.size === 0 || isRestarting}
                      className="border-yellow-500/50 text-yellow-600 hover:bg-yellow-500/10"
                    >
                      <RotateCcw className="h-3.5 w-3.5 mr-1.5" />
                      Restart App
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setShowRebootDialog(true)}
                      disabled={selectedDeviceIds.size === 0 || isRestarting}
                      className="border-red-500/50 text-red-600 hover:bg-red-500/10"
                    >
                      <Power className="h-3.5 w-3.5 mr-1.5" />
                      Reboot Device
                    </Button>
                  </div>
                  <p className="text-xs text-muted-foreground mt-2">
                    Restart App: Soft restart (app only, ~10s). Reboot Device: Hard restart (full device, ~30s).
                  </p>
                </div>

                <div className="rounded-lg bg-muted/50 p-4 text-sm text-muted-foreground">
                  <p className="font-medium mb-2">Note:</p>
                  <p>Screen streaming requires the Android agent to be updated with remote control capabilities. The backend is ready to receive streams.</p>
                </div>
              </div>
            </div>

            {viewingDeviceId && (
              <div className="mt-6">
                <DeviceScreenViewer
                  deviceId={viewingDeviceId}
                  deviceAlias={devices.find(d => d.id === viewingDeviceId)?.alias || 'Unknown Device'}
                  onClose={() => setViewingDeviceId(null)}
                />
              </div>
            )}
          </>
        )}
      </main>

      <SettingsDrawer
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
      />

      <AlertDialog open={showRestartAppDialog} onOpenChange={setShowRestartAppDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Restart UNITYmdm App?</AlertDialogTitle>
            <AlertDialogDescription>
              This will perform a soft restart of the UNITYmdm app on {selectedDeviceIds.size} selected device(s).
              <br /><br />
              <span className="font-medium">What happens:</span>
              <ul className="list-disc list-inside mt-2 space-y-1">
                <li>App will stop and restart automatically</li>
                <li>Devices will be back online in ~10 seconds</li>
                <li>All monitoring will resume automatically</li>
                <li>No interruption to other device functions</li>
              </ul>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction 
              onClick={handleRestartApp}
              className="bg-yellow-600 hover:bg-yellow-700"
            >
              Restart App
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={showRebootDialog} onOpenChange={setShowRebootDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Reboot Device?</AlertDialogTitle>
            <AlertDialogDescription>
              This will perform a <span className="font-semibold text-red-600">hard restart</span> of {selectedDeviceIds.size} selected device(s).
              <br /><br />
              <span className="font-medium">What happens:</span>
              <ul className="list-disc list-inside mt-2 space-y-1">
                <li>Entire device will reboot immediately</li>
                <li>All apps and processes will be interrupted</li>
                <li>Devices will be back online in ~30-60 seconds</li>
                <li>Monitoring will auto-resume after boot</li>
              </ul>
              <br />
              <span className="text-red-600 font-medium">⚠️ Use only when necessary (frozen devices, critical issues)</span>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction 
              onClick={handleReboot}
              className="bg-red-600 hover:bg-red-700"
            >
              Reboot Device
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
