"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { Header } from "@/components/header"
import { PageHeader } from "@/components/page-header"
import { Terminal, Play, Eye, Download, Clock, CheckCircle2, XCircle, AlertCircle, X } from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Checkbox } from "@/components/ui/checkbox"
import { Textarea } from "@/components/ui/textarea"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Badge } from "@/components/ui/badge"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useToast } from "@/hooks/use-toast"
import { isAuthenticated } from "@/lib/api-client"

interface ExecResult {
  device_id: string
  alias: string
  status: string
  exit_code?: number
  output?: string
  error?: string
  updated_at?: string
}

interface RecentExec {
  exec_id: string
  mode: string
  status: string
  created_at: string
  created_by: string
  stats: {
    total_targets: number
    sent_count: number
    acked_count: number
    error_count: number
  }
}

interface Device {
  id: string
  alias: string
  status: string
  last_seen: string
}

const FCM_PRESETS = {
  ping: { type: "ping" },
  ring: { type: "ring", duration: "30" },
  reboot: { type: "reboot", reason: "remote_exec" },
  launch_app: { type: "launch_app", package_name: "com.example.app" },
  clear_app_data: { type: "clear_app_data", package_name: "com.example.app" },
  enable_dnd: { type: "set_dnd", enable: "true" },
  disable_dnd: { type: "set_dnd", enable: "false" }
}

const SHELL_PRESETS = {
  suppress_wea: "settings put global zen_mode 2 && settings put global emergency_tone 0 && settings put global emergency_alerts_enabled 0",
  restore_normal: "settings put global zen_mode 0 && settings put global emergency_tone 1 && settings put global emergency_alerts_enabled 1"
}

export default function RemoteExecutionPage() {
  const router = useRouter()
  const { toast } = useToast()
  const [authChecked, setAuthChecked] = useState(false)
  
  const [scopeType, setScopeType] = useState<"all" | "filter" | "aliases">("all")
  const [deviceAliases, setDeviceAliases] = useState("")
  const [selectedDeviceIds, setSelectedDeviceIds] = useState<string[]>([])
  const [onlineOnly, setOnlineOnly] = useState(false)
  const [allDevices, setAllDevices] = useState<Device[]>([])
  const [isLoadingDevices, setIsLoadingDevices] = useState(false)
  
  const [mode, setMode] = useState<"fcm" | "shell">("fcm")
  const [fcmPayload, setFcmPayload] = useState("")
  const [shellCommand, setShellCommand] = useState("")
  const [selectedPreset, setSelectedPreset] = useState<string>("")
  const [selectedShellPreset, setSelectedShellPreset] = useState<string>("")
  
  const [dryRun, setDryRun] = useState(false)
  const [requireConfirmation, setRequireConfirmation] = useState(true)
  
  const [isPreviewing, setIsPreviewing] = useState(false)
  const [previewCount, setPreviewCount] = useState<number | null>(null)
  const [previewSample, setPreviewSample] = useState<Array<{id: string, alias: string}>>([])
  
  const [isExecuting, setIsExecuting] = useState(false)
  const [execId, setExecId] = useState<string | null>(null)
  const [results, setResults] = useState<ExecResult[]>([])
  const [stats, setStats] = useState({ sent: 0, acked: 0, errors: 0 })
  
  const [recentExecutions, setRecentExecutions] = useState<RecentExec[]>([])
  const [isPolling, setIsPolling] = useState(false)

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push('/login')
    } else {
      setAuthChecked(true)
    }
  }, [router])

  useEffect(() => {
    if (authChecked) {
      fetchRecentExecutions()
      fetchAllDevices()
    }
  }, [authChecked])

  useEffect(() => {
    let interval: NodeJS.Timeout | null = null
    if (isPolling && execId) {
      interval = setInterval(() => {
        fetchExecutionStatus(execId)
      }, 2000)
    }
    return () => {
      if (interval) clearInterval(interval)
    }
  }, [isPolling, execId])

  const getAuthToken = (): string | null => {
    if (typeof window === 'undefined') return null
    return localStorage.getItem('auth_token')
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

  const fetchRecentExecutions = async () => {
    try {
      const token = getAuthToken()
      if (!token) return

      const response = await fetch("/api/proxy/v1/remote-exec?limit=10", {
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
        setRecentExecutions(data.executions || [])
      }
    } catch (error) {
      console.error("Failed to fetch recent executions:", error)
    }
  }

  const fetchExecutionStatus = async (id: string) => {
    try {
      const token = getAuthToken()
      if (!token) return

      const response = await fetch(`/api/proxy/v1/remote-exec/${id}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      })
      
      if (response.ok) {
        const data = await response.json()
        setResults(data.results || [])
        setStats({
          sent: data.stats.sent_count,
          acked: data.stats.acked_count,
          errors: data.stats.error_count
        })
        
        if (data.status === 'completed') {
          setIsPolling(false)
        }
      }
    } catch (error) {
      console.error("Failed to fetch execution status:", error)
    }
  }

  const handlePreview = async () => {
    const token = getAuthToken()
    if (!token) return

    setIsPreviewing(true)
    try {
      const targets = buildTargets()
      const payload = mode === "fcm" ? getFcmPayload() : null
      const command = mode === "shell" ? shellCommand : null

      const response = await fetch("/api/proxy/v1/remote-exec", {
        method: "POST",
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          mode,
          targets,
          payload,
          command,
          dry_run: true
        })
      })

      if (response.status === 401) {
        router.push('/login')
        return
      }

      if (response.ok) {
        const data = await response.json()
        setPreviewCount(data.estimated_count)
        setPreviewSample(data.sample_aliases || [])
        toast({
          title: "Preview Ready",
          description: `${data.estimated_count} device(s) will be targeted`
        })
      } else {
        const error = await response.json()
        toast({
          title: "Preview Failed",
          description: error.detail || "Failed to preview targets",
          variant: "destructive"
        })
      }
    } catch (error) {
      if (error instanceof Error) {
        toast({
          title: "Validation Error",
          description: error.message,
          variant: "destructive"
        })
      } else {
        toast({
          title: "Error",
          description: "Failed to preview targets",
          variant: "destructive"
        })
      }
    } finally {
      setIsPreviewing(false)
    }
  }

  const handleExecute = async () => {
    const token = getAuthToken()
    if (!token) return

    if (requireConfirmation && previewCount && previewCount > 25) {
      const confirmed = confirm(`You are about to execute this command on ${previewCount} devices. Continue?`)
      if (!confirmed) return
    }

    setIsExecuting(true)
    try {
      const targets = buildTargets()
      const payload = mode === "fcm" ? getFcmPayload() : null
      const command = mode === "shell" ? shellCommand : null

      const response = await fetch("/api/proxy/v1/remote-exec", {
        method: "POST",
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          mode,
          targets,
          payload,
          command,
          dry_run: false
        })
      })

      if (response.status === 401) {
        router.push('/login')
        return
      }

      if (response.ok) {
        const data = await response.json()
        setExecId(data.exec_id)
        setIsPolling(true)
        toast({
          title: "Execution Started",
          description: `Command sent to ${data.sent_count} device(s)`
        })
        fetchRecentExecutions()
      } else {
        const error = await response.json()
        toast({
          title: "Execution Failed",
          description: error.detail || "Failed to execute command",
          variant: "destructive"
        })
      }
    } catch (error) {
      if (error instanceof Error) {
        toast({
          title: "Validation Error",
          description: error.message,
          variant: "destructive"
        })
      } else {
        toast({
          title: "Error",
          description: "Failed to execute command",
          variant: "destructive"
        })
      }
    } finally {
      setIsExecuting(false)
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
    setSelectedDeviceIds(allDevices.map(d => d.id))
  }

  const clearAllDevices = () => {
    setSelectedDeviceIds([])
  }

  const buildTargets = () => {
    if (scopeType === "all") {
      return { all: true }
    } else if (scopeType === "filter") {
      const filter: any = {}
      if (onlineOnly) filter.online = true
      return { filter }
    } else if (scopeType === "aliases") {
      if (selectedDeviceIds.length === 0) {
        throw new Error("Please select at least one device")
      }
      const selectedDevices = allDevices.filter(d => selectedDeviceIds.includes(d.id))
      const aliases = selectedDevices.map(d => d.alias)
      return { aliases }
    }
    return { all: true }
  }

  const getFcmPayload = () => {
    try {
      const parsed = JSON.parse(fcmPayload || "{}")
      if (Object.keys(parsed).length === 0 && fcmPayload.trim() !== "" && fcmPayload.trim() !== "{}") {
        toast({
          title: "Invalid JSON",
          description: "FCM payload must be valid JSON",
          variant: "destructive"
        })
        throw new Error("Invalid JSON payload")
      }
      return parsed
    } catch (e) {
      if (e instanceof SyntaxError) {
        toast({
          title: "Invalid JSON",
          description: "Failed to parse FCM payload. Please check your JSON syntax.",
          variant: "destructive"
        })
      }
      throw e
    }
  }

  const applyPreset = (presetName: string) => {
    const preset = FCM_PRESETS[presetName as keyof typeof FCM_PRESETS]
    if (preset) {
      setFcmPayload(JSON.stringify(preset, null, 2))
      setSelectedPreset(presetName)
    }
  }

  const applyShellPreset = (presetName: string) => {
    const preset = SHELL_PRESETS[presetName as keyof typeof SHELL_PRESETS]
    if (preset) {
      setShellCommand(preset)
      setSelectedShellPreset(presetName)
    }
  }

  const downloadCSV = () => {
    const headers = ["Alias", "Device ID", "Status", "Exit Code", "Output", "Error", "Timestamp"]
    
    const escapeCsvCell = (cell: string | number | null | undefined): string => {
      if (cell == null) return '""'
      const str = String(cell)
      // Escape quotes by doubling them and wrap in quotes if contains special chars
      if (str.includes('"') || str.includes(',') || str.includes('\n') || str.includes('\r')) {
        return `"${str.replace(/"/g, '""')}"`
      }
      return `"${str}"`
    }
    
    const rows = results.map(r => [
      escapeCsvCell(r.alias),
      escapeCsvCell(r.device_id),
      escapeCsvCell(r.status),
      escapeCsvCell(r.exit_code?.toString() || ""),
      escapeCsvCell(r.output || ""),
      escapeCsvCell(r.error || ""),
      escapeCsvCell(r.updated_at || "")
    ])
    
    const csv = [headers.map(escapeCsvCell), ...rows].map(row => row.join(",")).join("\n")
    const blob = new Blob([csv], { type: "text/csv" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `remote-exec-${execId}-${Date.now()}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  if (!authChecked) {
    return null
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <Header />
      <div className="container mx-auto p-6">
        <PageHeader 
          title="Remote Execution"
          description="Execute FCM commands or shell commands on device fleet"
          icon={<Terminal className="w-8 h-8" />}
        />

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-6">
          <div className="lg:col-span-2 space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>1. Target Devices</CardTitle>
                <CardDescription>Select which devices to execute commands on</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label>Scope</Label>
                  <Select value={scopeType} onValueChange={(v: any) => setScopeType(v)}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">Entire Fleet</SelectItem>
                      <SelectItem value="filter">Filtered Set</SelectItem>
                      <SelectItem value="aliases">Device Aliases</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {scopeType === "filter" && (
                  <div className="flex items-center space-x-2">
                    <Checkbox 
                      id="online" 
                      checked={onlineOnly} 
                      onCheckedChange={(checked) => setOnlineOnly(checked as boolean)}
                    />
                    <Label htmlFor="online">Online devices only</Label>
                  </div>
                )}

                {scopeType === "aliases" && (
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
                          Select All
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
                      <div className="flex flex-wrap gap-2 p-3 bg-gray-50 dark:bg-gray-800 rounded-lg border">
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
                        <div className="p-8 text-center text-gray-500">
                          Loading devices...
                        </div>
                      ) : allDevices.length === 0 ? (
                        <div className="p-8 text-center text-gray-500">
                          No devices enrolled
                        </div>
                      ) : (
                        <div className="divide-y">
                          {allDevices.map(device => (
                            <div
                              key={device.id}
                              className="flex items-center p-3 hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer"
                              onClick={() => toggleDeviceSelection(device.id)}
                            >
                              <Checkbox
                                checked={selectedDeviceIds.includes(device.id)}
                                onCheckedChange={() => toggleDeviceSelection(device.id)}
                                className="mr-3"
                              />
                              <div className="flex-1">
                                <div className="font-medium">{device.alias}</div>
                                <div className="text-xs text-gray-500">{device.id}</div>
                              </div>
                              <Badge variant={device.status === "online" ? "default" : "secondary"}>
                                {device.status}
                              </Badge>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}

                <Button onClick={handlePreview} disabled={isPreviewing} variant="outline">
                  <Eye className="w-4 h-4 mr-2" />
                  {isPreviewing ? "Previewing..." : "Preview Targets"}
                </Button>

                {previewCount !== null && (
                  <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                    <p className="font-medium">{previewCount} devices will be targeted</p>
                    {previewSample.length > 0 && (
                      <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                        Sample: {previewSample.map(d => d.alias).join(", ")}
                      </p>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>2. Command</CardTitle>
                <CardDescription>Configure the command to execute</CardDescription>
              </CardHeader>
              <CardContent>
                <Tabs value={mode} onValueChange={(v: any) => setMode(v)}>
                  <TabsList className="grid w-full grid-cols-2">
                    <TabsTrigger value="fcm">FCM (JSON)</TabsTrigger>
                    <TabsTrigger value="shell">Shell (Restricted)</TabsTrigger>
                  </TabsList>

                  <TabsContent value="fcm" className="space-y-4">
                    <div className="space-y-2">
                      <Label>Preset Commands</Label>
                      <Select value={selectedPreset} onValueChange={applyPreset}>
                        <SelectTrigger>
                          <SelectValue placeholder="Select a preset..." />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="ping">Ping</SelectItem>
                          <SelectItem value="ring">Ring</SelectItem>
                          <SelectItem value="reboot">Reboot</SelectItem>
                          <SelectItem value="launch_app">Launch App</SelectItem>
                          <SelectItem value="clear_app_data">Clear App Data</SelectItem>
                          <SelectItem value="enable_dnd">Enable Do Not Disturb (API)</SelectItem>
                          <SelectItem value="disable_dnd">Disable Do Not Disturb (API)</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="fcmPayload">JSON Payload</Label>
                      <Textarea
                        id="fcmPayload"
                        placeholder='{"type": "ping"}'
                        value={fcmPayload}
                        onChange={(e) => setFcmPayload(e.target.value)}
                        rows={8}
                        className="font-mono text-sm"
                      />
                    </div>
                  </TabsContent>

                  <TabsContent value="shell" className="space-y-4">
                    <div className="space-y-2">
                      <Label>Preset Commands</Label>
                      <Select value={selectedShellPreset} onValueChange={applyShellPreset}>
                        <SelectTrigger>
                          <SelectValue placeholder="Select a preset..." />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="suppress_wea">Suppress WEA & Enable DND</SelectItem>
                          <SelectItem value="restore_normal">Restore Normal Mode</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="shellCommand">Shell Command</Label>
                      <Input
                        id="shellCommand"
                        placeholder="am start -n com.minutes.unity/.MainActivity"
                        value={shellCommand}
                        onChange={(e) => setShellCommand(e.target.value)}
                        className="font-mono"
                      />
                      <p className="text-xs text-gray-500">
                        Only allow-listed commands are permitted. 
                        <a href="#" className="text-blue-600 ml-1">What's allowed?</a>
                      </p>
                    </div>
                  </TabsContent>
                </Tabs>

                <div className="space-y-3 mt-6">
                  <div className="flex items-center space-x-2">
                    <Checkbox 
                      id="dryRun" 
                      checked={dryRun} 
                      onCheckedChange={(checked) => setDryRun(checked as boolean)}
                    />
                    <Label htmlFor="dryRun">Dry run (validate only)</Label>
                  </div>

                  <div className="flex items-center space-x-2">
                    <Checkbox 
                      id="requireConfirmation" 
                      checked={requireConfirmation} 
                      onCheckedChange={(checked) => setRequireConfirmation(checked as boolean)}
                    />
                    <Label htmlFor="requireConfirmation">Require confirmation for large fleets</Label>
                  </div>
                </div>

                <Button 
                  onClick={handleExecute} 
                  disabled={isExecuting || (mode === "fcm" && (!fcmPayload || !fcmPayload.trim())) || (mode === "shell" && (!shellCommand || !shellCommand.trim()))}
                  className="w-full mt-4"
                >
                  <Play className="w-4 h-4 mr-2" />
                  {isExecuting ? "Executing..." : "Execute"}
                </Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle>3. Results</CardTitle>
                    <CardDescription>Real-time execution status</CardDescription>
                  </div>
                  {results.length > 0 && (
                    <Button onClick={downloadCSV} variant="outline" size="sm">
                      <Download className="w-4 h-4 mr-2" />
                      Download CSV
                    </Button>
                  )}
                </div>
              </CardHeader>
              <CardContent>
                {execId && (
                  <div className="grid grid-cols-3 gap-4 mb-6">
                    <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                      <div className="text-2xl font-bold">{stats.sent}</div>
                      <div className="text-sm text-gray-600 dark:text-gray-400">Sent</div>
                    </div>
                    <div className="p-4 bg-green-50 dark:bg-green-900/20 rounded-lg">
                      <div className="text-2xl font-bold">{stats.acked}</div>
                      <div className="text-sm text-gray-600 dark:text-gray-400">ACK OK</div>
                    </div>
                    <div className="p-4 bg-red-50 dark:bg-red-900/20 rounded-lg">
                      <div className="text-2xl font-bold">{stats.errors}</div>
                      <div className="text-sm text-gray-600 dark:text-gray-400">Errors</div>
                    </div>
                  </div>
                )}

                {results.length > 0 ? (
                  <div className="border rounded-lg overflow-auto max-h-96">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Alias</TableHead>
                          <TableHead>Status</TableHead>
                          <TableHead>Exit Code</TableHead>
                          <TableHead>Output</TableHead>
                          <TableHead>Timestamp</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {results.map((result) => (
                          <TableRow key={result.device_id}>
                            <TableCell className="font-medium">{result.alias}</TableCell>
                            <TableCell>
                              <Badge variant={
                                result.status === "OK" ? "default" :
                                result.status === "sent" ? "secondary" :
                                "destructive"
                              }>
                                {result.status}
                              </Badge>
                            </TableCell>
                            <TableCell>{result.exit_code ?? "-"}</TableCell>
                            <TableCell className="max-w-xs truncate text-xs font-mono">
                              {result.output || result.error || "-"}
                            </TableCell>
                            <TableCell className="text-xs">
                              {result.updated_at ? new Date(result.updated_at).toLocaleTimeString() : "-"}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                ) : (
                  <div className="text-center py-12 text-gray-500">
                    No results yet. Execute a command to see results.
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          <div>
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center">
                  <Clock className="w-4 h-4 mr-2" />
                  Recent Runs
                </CardTitle>
              </CardHeader>
              <CardContent>
                {recentExecutions.length > 0 ? (
                  <div className="space-y-3">
                    {recentExecutions.map((exec) => (
                      <div 
                        key={exec.exec_id}
                        className="p-3 border rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer transition-colors"
                        onClick={() => {
                          setExecId(exec.exec_id)
                          fetchExecutionStatus(exec.exec_id)
                        }}
                      >
                        <div className="flex items-center justify-between mb-1">
                          <Badge variant={exec.mode === "fcm" ? "default" : "secondary"}>
                            {exec.mode.toUpperCase()}
                          </Badge>
                          <span className="text-xs text-gray-500">
                            {new Date(exec.created_at).toLocaleDateString()}
                          </span>
                        </div>
                        <div className="text-sm space-y-1">
                          <div className="flex justify-between">
                            <span className="text-gray-600 dark:text-gray-400">Sent:</span>
                            <span className="font-medium">{exec.stats.sent_count}/{exec.stats.total_targets}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-gray-600 dark:text-gray-400">ACK:</span>
                            <span className="font-medium text-green-600">{exec.stats.acked_count}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-gray-600 dark:text-gray-400">Errors:</span>
                            <span className="font-medium text-red-600">{exec.stats.error_count}</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-8 text-sm text-gray-500">
                    No recent executions
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  )
}
