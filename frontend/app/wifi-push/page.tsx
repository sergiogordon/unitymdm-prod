"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { Header } from "@/components/header"
import { PageHeader } from "@/components/page-header"
import { Wifi, Play, Eye, CheckCircle2, XCircle, Clock, X } from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Checkbox } from "@/components/ui/checkbox"
import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useToast } from "@/hooks/use-toast"
import { isAuthenticated } from "@/lib/api-client"

interface Device {
  id: string
  alias: string
  status: string
  last_seen: string
}

interface PushResult {
  device_id: string
  alias: string
  ok: boolean
  message?: string
  error?: string
}

interface WiFiSettings {
  ssid: string
  password: string
  security_type: string
  enabled: boolean
}

export default function WiFiPushPage() {
  const router = useRouter()
  const { toast } = useToast()
  const [authChecked, setAuthChecked] = useState(false)
  
  const [scopeType, setScopeType] = useState<"all" | "filter" | "specific">("all")
  const [selectedDeviceIds, setSelectedDeviceIds] = useState<string[]>([])
  const [onlineOnly, setOnlineOnly] = useState(true)
  const [allDevices, setAllDevices] = useState<Device[]>([])
  const [isLoadingDevices, setIsLoadingDevices] = useState(false)
  
  const [isPreviewing, setIsPreviewing] = useState(false)
  const [previewCount, setPreviewCount] = useState<number | null>(null)
  const [previewSample, setPreviewSample] = useState<Array<{id: string, alias: string}>>([])
  
  const [isPushing, setIsPushing] = useState(false)
  const [results, setResults] = useState<PushResult[]>([])
  const [pushStats, setPushStats] = useState({ total: 0, success: 0, failed: 0 })
  
  const [wifiSettings, setWifiSettings] = useState<WiFiSettings | null>(null)
  const [isLoadingSettings, setIsLoadingSettings] = useState(true)

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push('/login')
    } else {
      setAuthChecked(true)
    }
  }, [router])

  useEffect(() => {
    if (authChecked) {
      fetchWiFiSettings()
      fetchAllDevices()
    }
  }, [authChecked])

  const getAuthToken = (): string | null => {
    if (typeof window === 'undefined') return null
    return localStorage.getItem('auth_token')
  }

  const fetchWiFiSettings = async () => {
    try {
      const token = getAuthToken()
      if (!token) return

      const response = await fetch("/api/proxy/v1/settings/wifi", {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      })
      
      if (response.status === 401) {
        router.push('/login')
        return
      }
      
      if (response.ok) {
        const data = await response.json()
        setWifiSettings(data)
      }
    } catch (error) {
      console.error("Failed to fetch WiFi settings:", error)
    } finally {
      setIsLoadingSettings(false)
    }
  }

  const fetchAllDevices = async () => {
    setIsLoadingDevices(true)
    try {
      const token = getAuthToken()
      if (!token) return

      const response = await fetch("/api/proxy/v1/devices?page=1&limit=100", {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      })
      
      if (response.status === 401) {
        router.push('/login')
        return
      }
      
      if (response.ok) {
        const data = await response.json()
        setAllDevices(data.devices || [])
      }
    } catch (error) {
      console.error("Failed to fetch devices:", error)
    } finally {
      setIsLoadingDevices(false)
    }
  }

  const toggleDeviceSelection = (deviceId: string) => {
    setSelectedDeviceIds(prev => 
      prev.includes(deviceId) 
        ? prev.filter(id => id !== deviceId)
        : [...prev, deviceId]
    )
  }

  const selectAllDevices = () => {
    const filteredDevices = onlineOnly 
      ? allDevices.filter(d => d.status === 'online')
      : allDevices
    setSelectedDeviceIds(filteredDevices.map(d => d.id))
  }

  const clearAllDevices = () => {
    setSelectedDeviceIds([])
  }

  const handlePreview = async () => {
    setIsPreviewing(true)
    try {
      const token = getAuthToken()
      if (!token) {
        toast({
          title: "Error",
          description: "Not authenticated",
          variant: "destructive"
        })
        return
      }

      const deviceIds = getTargetDeviceIds()
      setPreviewCount(deviceIds.length)
      setPreviewSample(
        deviceIds.slice(0, 5).map(id => {
          const device = allDevices.find(d => d.id === id)
          return { id, alias: device?.alias || id }
        })
      )
      
      toast({
        title: "Preview Ready",
        description: `${deviceIds.length} device${deviceIds.length !== 1 ? 's' : ''} will receive WiFi credentials`
      })
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to generate preview",
        variant: "destructive"
      })
    } finally {
      setIsPreviewing(false)
    }
  }

  const getTargetDeviceIds = (): string[] => {
    if (scopeType === "all") {
      return onlineOnly 
        ? allDevices.filter(d => d.status === 'online').map(d => d.id)
        : allDevices.map(d => d.id)
    } else if (scopeType === "filter") {
      return onlineOnly 
        ? allDevices.filter(d => d.status === 'online').map(d => d.id)
        : allDevices.map(d => d.id)
    } else {
      return selectedDeviceIds
    }
  }

  const handlePushWiFi = async () => {
    if (!wifiSettings || !wifiSettings.enabled) {
      toast({
        title: "Error",
        description: "WiFi settings not configured or disabled",
        variant: "destructive"
      })
      return
    }

    const deviceIds = getTargetDeviceIds()
    if (deviceIds.length === 0) {
      toast({
        title: "Error",
        description: "No devices selected",
        variant: "destructive"
      })
      return
    }

    setIsPushing(true)
    setResults([])
    setPushStats({ total: 0, success: 0, failed: 0 })

    try {
      const token = getAuthToken()
      if (!token) {
        toast({
          title: "Error",
          description: "Not authenticated",
          variant: "destructive"
        })
        return
      }

      toast({
        title: "Pushing WiFi Credentials",
        description: `Sending to ${deviceIds.length} device${deviceIds.length !== 1 ? 's' : ''}...`
      })

      const response = await fetch("/api/proxy/v1/wifi/push-to-devices", {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ device_ids: deviceIds })
      })
      
      if (response.status === 401) {
        router.push('/login')
        return
      }
      
      if (response.ok) {
        const data = await response.json()
        setResults(data.results || [])
        setPushStats({
          total: data.total || 0,
          success: data.success_count || 0,
          failed: data.failed_count || 0
        })
        
        toast({
          title: "WiFi Push Complete",
          description: `${data.success_count}/${data.total} devices reached successfully`
        })
      } else {
        const error = await response.json()
        toast({
          title: "Error",
          description: error.detail || "Failed to push WiFi credentials",
          variant: "destructive"
        })
      }
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to push WiFi credentials",
        variant: "destructive"
      })
    } finally {
      setIsPushing(false)
    }
  }

  if (!authChecked) {
    return <div className="flex items-center justify-center min-h-screen">Loading...</div>
  }

  const filteredDevices = scopeType === "specific" 
    ? (onlineOnly ? allDevices.filter(d => d.status === 'online') : allDevices)
    : []

  return (
    <div className="min-h-screen bg-background">
      <Header />
      
      <main className="container mx-auto px-4 py-8 max-w-7xl">
        <PageHeader 
          icon={Wifi}
          title="WiFi Push"
          description="Push WiFi credentials to devices via FCM"
        />

        {isLoadingSettings ? (
          <Card>
            <CardContent className="py-8">
              <div className="text-center text-muted-foreground">Loading WiFi settings...</div>
            </CardContent>
          </Card>
        ) : !wifiSettings || !wifiSettings.enabled ? (
          <Card>
            <CardContent className="py-8">
              <div className="text-center space-y-4">
                <p className="text-muted-foreground">WiFi settings not configured or disabled</p>
                <Button onClick={() => router.push('/')}>
                  Configure WiFi Settings
                </Button>
              </div>
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Current WiFi Configuration</CardTitle>
                <CardDescription>These credentials will be pushed to selected devices</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">SSID:</span>
                    <code className="px-2 py-1 bg-muted rounded">{wifiSettings.ssid}</code>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium">Security:</span>
                    <Badge variant="secondary">{wifiSettings.security_type.toUpperCase()}</Badge>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium">Status:</span>
                    <Badge variant="default">Enabled</Badge>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Target Devices</CardTitle>
                <CardDescription>Select which devices should receive the WiFi credentials</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-3">
                  <Label>Targeting Mode</Label>
                  <div className="space-y-2">
                    <div className="flex items-center space-x-2">
                      <input
                        type="radio"
                        id="all"
                        checked={scopeType === "all"}
                        onChange={() => setScopeType("all")}
                        className="cursor-pointer"
                      />
                      <Label htmlFor="all" className="cursor-pointer font-normal">
                        All devices {onlineOnly && "(online only)"}
                      </Label>
                    </div>
                    
                    <div className="flex items-center space-x-2">
                      <input
                        type="radio"
                        id="filter"
                        checked={scopeType === "filter"}
                        onChange={() => setScopeType("filter")}
                        className="cursor-pointer"
                      />
                      <Label htmlFor="filter" className="cursor-pointer font-normal">
                        Filtered devices
                      </Label>
                    </div>
                    
                    <div className="flex items-center space-x-2">
                      <input
                        type="radio"
                        id="specific"
                        checked={scopeType === "specific"}
                        onChange={() => setScopeType("specific")}
                        className="cursor-pointer"
                      />
                      <Label htmlFor="specific" className="cursor-pointer font-normal">
                        Select specific devices
                      </Label>
                    </div>
                  </div>
                </div>

                <div className="flex items-center space-x-2">
                  <Checkbox 
                    id="online" 
                    checked={onlineOnly} 
                    onCheckedChange={(checked) => setOnlineOnly(checked as boolean)}
                  />
                  <Label htmlFor="online" className="cursor-pointer">Online devices only</Label>
                </div>

                {scopeType === "specific" && (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <Label>Select Devices ({selectedDeviceIds.length} selected)</Label>
                      <div className="flex gap-2">
                        <Button 
                          type="button"
                          onClick={selectAllDevices} 
                          variant="ghost" 
                          size="sm"
                          disabled={isLoadingDevices}
                        >
                          Select All {onlineOnly && "Online"}
                        </Button>
                        <Button 
                          type="button"
                          onClick={clearAllDevices} 
                          variant="ghost" 
                          size="sm"
                          disabled={selectedDeviceIds.length === 0}
                        >
                          Clear
                        </Button>
                      </div>
                    </div>

                    {selectedDeviceIds.length > 0 && (
                      <div className="flex flex-wrap gap-2 p-3 bg-muted rounded-lg border">
                        {allDevices
                          .filter(d => selectedDeviceIds.includes(d.id))
                          .map(device => (
                            <Badge key={device.id} variant="secondary" className="pl-3 pr-1 py-1">
                              {device.alias}
                              <button
                                onClick={() => toggleDeviceSelection(device.id)}
                                className="ml-1 hover:bg-gray-300 dark:hover:bg-gray-600 rounded-full p-0.5"
                              >
                                <X className="w-3 h-3" />
                              </button>
                            </Badge>
                          ))}
                      </div>
                    )}

                    <div className="border rounded-lg max-h-64 overflow-y-auto">
                      {isLoadingDevices ? (
                        <div className="p-4 text-center text-muted-foreground">Loading devices...</div>
                      ) : (
                        <div className="divide-y">
                          {filteredDevices.map(device => (
                            <div 
                              key={device.id}
                              className="flex items-center gap-3 p-3 hover:bg-muted/50 cursor-pointer"
                              onClick={() => toggleDeviceSelection(device.id)}
                            >
                              <Checkbox 
                                checked={selectedDeviceIds.includes(device.id)}
                                onCheckedChange={() => toggleDeviceSelection(device.id)}
                              />
                              <div className="flex-1">
                                <div className="font-medium">{device.alias}</div>
                                <div className="text-sm text-muted-foreground">
                                  {device.status === 'online' ? (
                                    <span className="text-green-600">● Online</span>
                                  ) : (
                                    <span className="text-gray-500">● Offline</span>
                                  )}
                                </div>
                              </div>
                            </div>
                          ))}
                          {filteredDevices.length === 0 && (
                            <div className="p-4 text-center text-muted-foreground">
                              No {onlineOnly && "online "}devices available
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {previewCount !== null && (
                  <div className="p-4 bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded-lg">
                    <div className="space-y-2">
                      <div className="flex items-center gap-2">
                        <Eye className="h-4 w-4 text-blue-600" />
                        <span className="font-medium">Preview: {previewCount} device{previewCount !== 1 ? 's' : ''} will receive credentials</span>
                      </div>
                      {previewSample.length > 0 && (
                        <div className="text-sm text-muted-foreground">
                          Sample: {previewSample.map(d => d.alias).join(', ')}
                          {previewCount > 5 && ` and ${previewCount - 5} more...`}
                        </div>
                      )}
                    </div>
                  </div>
                )}

                <div className="flex gap-2">
                  <Button 
                    onClick={handlePreview}
                    variant="outline"
                    disabled={isPreviewing || isPushing}
                  >
                    <Eye className="h-4 w-4 mr-2" />
                    Preview
                  </Button>
                  <Button 
                    onClick={handlePushWiFi}
                    disabled={isPushing || isPreviewing}
                  >
                    <Play className="h-4 w-4 mr-2" />
                    {isPushing ? "Pushing..." : "Push WiFi Credentials"}
                  </Button>
                </div>
              </CardContent>
            </Card>

            {results.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>Push Results</CardTitle>
                  <CardDescription>
                    {pushStats.success}/{pushStats.total} devices successfully received credentials
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="mb-4 flex gap-4">
                    <div className="flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4 text-green-600" />
                      <span className="text-sm">Success: {pushStats.success}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <XCircle className="h-4 w-4 text-red-600" />
                      <span className="text-sm">Failed: {pushStats.failed}</span>
                    </div>
                  </div>
                  
                  <div className="border rounded-lg overflow-hidden">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Device</TableHead>
                          <TableHead>Status</TableHead>
                          <TableHead>Message</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {results.map((result, idx) => (
                          <TableRow key={idx}>
                            <TableCell className="font-medium">{result.alias || result.device_id}</TableCell>
                            <TableCell>
                              {result.ok ? (
                                <Badge variant="default" className="bg-green-600">
                                  <CheckCircle2 className="h-3 w-3 mr-1" />
                                  Success
                                </Badge>
                              ) : (
                                <Badge variant="destructive">
                                  <XCircle className="h-3 w-3 mr-1" />
                                  Failed
                                </Badge>
                              )}
                            </TableCell>
                            <TableCell className="text-sm text-muted-foreground">
                              {result.message || result.error || 'N/A'}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        )}
      </main>
    </div>
  )
}
