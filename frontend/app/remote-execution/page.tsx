"use client"

import { useState, useEffect, useMemo } from "react"
import { useRouter } from "next/navigation"
import { Header } from "@/components/header"
import { PageHeader } from "@/components/page-header"
import { Terminal, Play, Eye, Download, Clock, CheckCircle2, XCircle, AlertCircle, X, Search } from "lucide-react"
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
import { buildBloatwareDisableCommand } from "@/lib/bloatwarePreset"

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
  launch_unity_app: { type: "launch_app", package_name: "io.unitynodes.unityapp" },
  launch_app: { type: "launch_app", package_name: "com.example.app" },
  force_stop_unity_app: { type: "force_stop_app", package_name: "io.unitynodes.unityapp" },
  clear_app_data: { type: "clear_app_data", package_name: "com.example.app" },
  enable_dnd: { type: "set_dnd", enable: "true" },
  disable_dnd: { type: "set_dnd", enable: "false" },
  exempt_unity_app: { type: "exempt_unity_app" },
  enable_stay_awake: { type: "enable_stay_awake" },
  soft_update_refresh: { type: "soft_update_refresh" } // Special preset - handled separately
}

const SHELL_PRESETS = {
  launch_unity_app: "monkey -p io.unitynodes.unityapp -c android.intent.category.LAUNCHER 1",
  suppress_wea: "settings put global zen_mode 2 && settings put global emergency_tone 0 && settings put global emergency_alerts_enabled 0",
  restore_normal: "settings put global zen_mode 0 && settings put global emergency_tone 1 && settings put global emergency_alerts_enabled 1",
  enable_auto_update: "settings put global auto_system_update_policy 1",
  disable_auto_update: "settings put global auto_system_update_policy 0",
  trigger_update_service: "cmd jobscheduler run -f android/com.android.server.update.SystemUpdateService 1",
  check_os_version: "getprop ro.build.version.release",
  check_security_patch: "getprop ro.build.version.security_patch",
  enable_stay_awake: "settings put global stay_on_while_plugged_in 7"
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
  const [resultFilter, setResultFilter] = useState("")
  
  const [isRestartingApp, setIsRestartingApp] = useState(false)
  const [restartAppPackage, setRestartAppPackage] = useState("io.unitynodes.unityapp")
  const [restartAppResults, setRestartAppResults] = useState<any>(null)
  const [isPollingRestart, setIsPollingRestart] = useState(false)
  const [restartId, setRestartId] = useState<string | null>(null)
  const [restartPollStartTime, setRestartPollStartTime] = useState<number | null>(null)
  
  const [isReinstallingUnity, setIsReinstallingUnity] = useState(false)
  const [reinstallExecId, setReinstallExecId] = useState<string | null>(null)
  const [isPollingReinstall, setIsPollingReinstall] = useState(false)
  const [reinstallResults, setReinstallResults] = useState<any>(null)
  const [reinstallPollStartTime, setReinstallPollStartTime] = useState<number | null>(null)
  const [deviceFilter, setDeviceFilter] = useState("")
  
  const RESTART_POLL_TIMEOUT_MS = 60000

  const filteredDevicesForSelector = useMemo(() => {
    let result = [...allDevices]
    
    if (deviceFilter.trim()) {
      const filterLower = deviceFilter.toLowerCase()
      result = result.filter(device => 
        device.alias.toLowerCase().startsWith(filterLower)
      )
    }
    
    result.sort((a, b) => {
      const aAlias = a.alias.toUpperCase()
      const bAlias = b.alias.toUpperCase()
      const aStartsWithS = aAlias.startsWith('S')
      const bStartsWithS = bAlias.startsWith('S')
      const aStartsWithD = aAlias.startsWith('D')
      const bStartsWithD = bAlias.startsWith('D')
      
      if (aStartsWithS && !bStartsWithS) return -1
      if (!aStartsWithS && bStartsWithS) return 1
      
      if (aStartsWithD && !bStartsWithD && !bStartsWithS) return -1
      if (!aStartsWithD && bStartsWithD && !aStartsWithS) return 1
      
      const aMatch = aAlias.match(/^([A-Z]+)(\d+)?/)
      const bMatch = bAlias.match(/^([A-Z]+)(\d+)?/)
      
      if (aMatch && bMatch) {
        const aPrefix = aMatch[1]
        const bPrefix = bMatch[1]
        
        if (aPrefix !== bPrefix) {
          return aPrefix.localeCompare(bPrefix)
        }
        
        const aNum = aMatch[2] ? parseInt(aMatch[2], 10) : 0
        const bNum = bMatch[2] ? parseInt(bMatch[2], 10) : 0
        return aNum - bNum
      }
      
      return aAlias.localeCompare(bAlias)
    })
    
    return result
  }, [allDevices, deviceFilter])

  // Calculate if Execute button should be disabled
  const isExecuteDisabled = useMemo(() => {
    let disabled = false
    // Allow execution if soft_update_refresh preset is selected (even with empty payload)
    if (mode === "fcm" && selectedPreset === "soft_update_refresh") {
      disabled = isExecuting
      console.log("[BUTTON-DISABLED] soft_update_refresh selected", { disabled, isExecuting })
    } else if (mode === "fcm" && (!fcmPayload || !fcmPayload.trim())) {
      // For other FCM commands, require a payload
      disabled = true
      console.log("[BUTTON-DISABLED] FCM mode with empty payload", { disabled, fcmPayload })
    } else if (mode === "shell" && (!shellCommand || !shellCommand.trim())) {
      // For shell commands, require a command
      disabled = true
      console.log("[BUTTON-DISABLED] Shell mode with empty command", { disabled, shellCommand })
    } else {
      disabled = isExecuting
      console.log("[BUTTON-DISABLED] Default case", { disabled, isExecuting })
    }
    return disabled
  }, [mode, selectedPreset, fcmPayload, shellCommand, isExecuting])

  const sortedResults = useMemo(() => {
    return [...results].sort((a, b) => {
      const aAlias = (a.alias || '').toUpperCase()
      const bAlias = (b.alias || '').toUpperCase()
      
      const aMatch = aAlias.match(/^([A-Z]+)(\d+)?/)
      const bMatch = bAlias.match(/^([A-Z]+)(\d+)?/)
      
      if (aMatch && bMatch) {
        const aPrefix = aMatch[1]
        const bPrefix = bMatch[1]
        
        if (aPrefix !== bPrefix) {
          return aPrefix.localeCompare(bPrefix)
        }
        
        const aNum = aMatch[2] ? parseInt(aMatch[2], 10) : 0
        const bNum = bMatch[2] ? parseInt(bMatch[2], 10) : 0
        return aNum - bNum
      }
      
      return aAlias.localeCompare(bAlias)
    })
  }, [results])

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

  useEffect(() => {
    let interval: NodeJS.Timeout | null = null
    if (isPollingRestart && restartId) {
      interval = setInterval(() => {
        fetchRestartAppStatus(restartId)
      }, 2000)
    }
    return () => {
      if (interval) clearInterval(interval)
    }
  }, [isPollingRestart, restartId])

  useEffect(() => {
    let interval: NodeJS.Timeout | null = null
    if (isPollingReinstall && reinstallExecId) {
      interval = setInterval(() => {
        fetchReinstallStatus(reinstallExecId)
      }, 2000)
    }
    return () => {
      if (interval) clearInterval(interval)
    }
  }, [isPollingReinstall, reinstallExecId])

  // Clear preview results when mode or target scope changes
  useEffect(() => {
    setPreviewCount(null)
    setPreviewSample([])
  }, [mode, scopeType])

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
      toast({
        title: "Warning",
        description: "Failed to load recent executions history",
        variant: "destructive"
      })
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
        
        if (data.status === 'completed' || data.status === 'failed') {
          setIsPolling(false)
        }
      }
    } catch (error) {
      console.error("Failed to fetch execution status:", error)
    }
  }

  const fetchRestartAppStatus = async (id: string) => {
    try {
      if (restartPollStartTime && Date.now() - restartPollStartTime > RESTART_POLL_TIMEOUT_MS) {
        setIsPollingRestart(false)
        setRestartPollStartTime(null)
        toast({
          title: "Restart App Timed Out",
          description: "Polling stopped after 60 seconds. Check device status manually.",
          variant: "destructive"
        })
        return
      }

      const token = getAuthToken()
      if (!token) return

      const response = await fetch(`/api/proxy/v1/remote-exec/restart-app/${id}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      })
      
      if (response.ok) {
        const data = await response.json()
        setRestartAppResults(data)
        
        const terminalStates = ['completed', 'failed', 'partial', 'timed_out', 'error']
        if (terminalStates.includes(data.status)) {
          setIsPollingRestart(false)
          setRestartPollStartTime(null)
          
          if (data.status !== 'completed') {
            const statsParts = []
            if (data.stats?.ok > 0) statsParts.push(`${data.stats.ok} OK`)
            if (data.stats?.failed > 0) statsParts.push(`${data.stats.failed} failed`)
            if (data.stats?.timed_out > 0) statsParts.push(`${data.stats.timed_out} timed out`)
            if (data.stats?.pending > 0) statsParts.push(`${data.stats.pending} pending`)
            
            toast({
              title: `Restart App ${data.status.charAt(0).toUpperCase() + data.status.slice(1).replace('_', ' ')}`,
              description: data.failure_reason || (statsParts.length > 0 ? statsParts.join(', ') : 'Unknown status'),
              variant: data.status === 'partial' ? 'default' : 'destructive'
            })
          }
        }
      } else {
        setIsPollingRestart(false)
        setRestartPollStartTime(null)
        toast({
          title: "Error",
          description: "Failed to fetch restart status",
          variant: "destructive"
        })
      }
    } catch (error) {
      console.error("Failed to fetch restart app status:", error)
      setIsPollingRestart(false)
      setRestartPollStartTime(null)
    }
  }

  const fetchReinstallStatus = async (execId: string) => {
    try {
      if (reinstallPollStartTime && Date.now() - reinstallPollStartTime > RESTART_POLL_TIMEOUT_MS) {
        setIsPollingReinstall(false)
        setReinstallPollStartTime(null)
        toast({
          title: "Reinstall Timed Out",
          description: "Polling stopped after 60 seconds. Check device status manually.",
          variant: "destructive"
        })
        return
      }

      const token = getAuthToken()
      if (!token) return

      const response = await fetch(`/api/proxy/v1/apk/reinstall-unity-and-launch/${execId}/status`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      })
      
      if (response.ok) {
        const data = await response.json()
        setReinstallResults(data)
        
        const terminalStates = ['ok', 'failed']
        if (data.status === 'ok' || data.status === 'failed') {
          setIsPollingReinstall(false)
          setReinstallPollStartTime(null)
          
          if (data.status === 'ok') {
            toast({
              title: "Soft Update Refresh Complete",
              description: `Successfully reinstalled and launched on ${data.stats?.ok || 0} device(s)`,
            })
          } else {
            const statsParts = []
            if (data.stats?.ok > 0) statsParts.push(`${data.stats.ok} OK`)
            if (data.stats?.failed > 0) statsParts.push(`${data.stats.failed} failed`)
            if (data.stats?.pending > 0) statsParts.push(`${data.stats.pending} pending`)
            
            toast({
              title: "Soft Update Refresh Failed",
              description: statsParts.length > 0 ? statsParts.join(', ') : 'Unknown status',
              variant: "destructive"
            })
          }
        }
      } else {
        setIsPollingReinstall(false)
        setReinstallPollStartTime(null)
        toast({
          title: "Error",
          description: "Failed to fetch reinstall status",
          variant: "destructive"
        })
      }
    } catch (error) {
      console.error("Failed to fetch reinstall status:", error)
      setIsPollingReinstall(false)
      setReinstallPollStartTime(null)
    }
  }

  const handleSoftUpdateRefresh = async () => {
    const token = getAuthToken()
    if (!token) {
      toast({
        title: "Session expired",
        description: "Please sign in again to continue.",
        variant: "destructive"
      })
      router.push("/login")
      return
    }

    // Get selected device IDs
    const deviceIds = scopeType === "aliases" 
      ? selectedDeviceIds 
      : (scopeType === "filter" 
        ? filteredDevicesForSelector.map(d => d.id)
        : allDevices.map(d => d.id))

    if (deviceIds.length === 0) {
      toast({
        title: "No devices selected",
        description: "Please select at least one device",
        variant: "destructive"
      })
      return
    }

    if (requireConfirmation && deviceIds.length > 25) {
      const confirmed = confirm(`You are about to reinstall Unity APK and launch on ${deviceIds.length} devices. Continue?`)
      if (!confirmed) return
    }

    setIsReinstallingUnity(true)
    
    try {
      const response = await fetch("/api/proxy/v1/apk/reinstall-unity-and-launch", {
        method: "POST",
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          device_ids: deviceIds,
          dry_run: false
        })
      })

      if (response.status === 401) {
        router.push('/login')
        return
      }

      if (response.ok) {
        const data = await response.json()
        setReinstallExecId(data.exec_id)
        setIsPollingReinstall(true)
        setReinstallPollStartTime(Date.now())
        toast({
          title: "Soft Update Refresh Started",
          description: `Reinstalling Unity APK on ${data.stats?.sent || 0} device(s)`
        })
        fetchRecentExecutions()
      } else {
        const errorText = await response.text()
        let errorDetail = "Failed to start reinstall"
        try {
          const error = JSON.parse(errorText)
          errorDetail = error.detail || errorDetail
        } catch (e) {
          errorDetail = errorText || errorDetail
        }
        
        toast({
          title: `Reinstall Failed (${response.status})`,
          description: errorDetail,
          variant: "destructive"
        })
      }
    } catch (error) {
      console.error("Failed to start reinstall:", error)
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to start reinstall",
        variant: "destructive"
      })
    } finally {
      setIsReinstallingUnity(false)
    }
  }

  const handleRestartApp = async () => {
    const token = getAuthToken()
    if (!token) {
      toast({
        title: "Session expired",
        description: "Please sign in again to continue.",
        variant: "destructive"
      })
      router.push("/login")
      return
    }

    if (scopeType === "aliases" && selectedDeviceIds.length === 0) {
      toast({
        title: "No devices selected",
        description: "Please select at least one device to restart the app on.",
        variant: "destructive"
      })
      return
    }

    setIsRestartingApp(true)
    setRestartAppResults(null)

    try {
      // Build request payload in format backend expects
      // Note: online_only defaults to false, so commands are sent to ALL devices by default
      // Offline devices will naturally timeout after 5 minutes if they don't respond
      let requestBody: any = {
        package_name: restartAppPackage,
        online_only: onlineOnly  // false by default = send to all devices
      }

      // Convert buildTargets() format to backend format
      if (scopeType === "all") {
        requestBody.scope_type = "all"
        // Don't send targets for "all" scope
      } else if (scopeType === "filter") {
        requestBody.scope_type = "all"
        // online_only is already set above
      } else if (scopeType === "aliases") {
        try {
          const selectedDevices = allDevices.filter(d => selectedDeviceIds.includes(d.id))
          const aliases = selectedDevices.map(d => d.alias)
          requestBody.scope_type = "aliases"
          requestBody.targets = { aliases }
        } catch (buildError) {
          console.error("[RESTART-APP] Error building aliases:", buildError)
          throw buildError
        }
      }

      console.log("[RESTART-APP] Sending request:", {
        package_name: requestBody.package_name,
        scope_type: requestBody.scope_type,
        online_only: requestBody.online_only,
        targets: requestBody.targets ? (requestBody.targets.aliases ? `${requestBody.targets.aliases.length} aliases` : `${requestBody.targets.device_ids?.length || 0} device_ids`) : "none"
      })
      
      const response = await fetch("/api/proxy/v1/remote-exec/restart-app", {
        method: "POST",
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestBody)
      })

      console.log("[RESTART-APP] Response status:", response.status, response.statusText)

      if (response.status === 401) {
        setIsRestartingApp(false)
        router.push('/login')
        return
      }

      if (response.ok) {
        const data = await response.json()
        console.log("[RESTART-APP] Success response:", data)
        setRestartId(data.restart_id)
        setRestartPollStartTime(Date.now())
        setIsPollingRestart(true)
        toast({
          title: "Restart App Started",
          description: `Force-stop sent to ${data.stats.force_stop.sent} devices, launch sent to ${data.stats.launch.sent} devices`
        })
        fetchRecentExecutions()
      } else {
        // Handle error response - might not be JSON
        // Read as text first to avoid "body already used" error when parsing JSON fails
        let errorMessage = "Failed to restart app"
        try {
          const errorText = await response.text()
          try {
            // Try to parse as JSON
            const errorData = JSON.parse(errorText)
            errorMessage = errorData.detail || errorMessage
            console.error("[RESTART-APP] Error response:", errorData)
          } catch (jsonError) {
            // Not valid JSON, use text directly
            console.error("[RESTART-APP] Non-JSON error response:", response.status, errorText)
            errorMessage = `Server error (${response.status}): ${errorText.substring(0, 100)}`
          }
        } catch (textError) {
          console.error("[RESTART-APP] Failed to read error response:", textError)
          errorMessage = `Server error (${response.status})`
        }
        toast({
          title: "Restart App Failed",
          description: errorMessage,
          variant: "destructive"
        })
      }
    } catch (error) {
      console.error("[RESTART-APP] Exception:", error)
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to restart app",
        variant: "destructive"
      })
    } finally {
      setIsRestartingApp(false)
    }
  }

  const handlePreview = async () => {
    const token = getAuthToken()
    if (!token) return

    // Validate command data before preview
    if (mode === "fcm" && selectedPreset !== "soft_update_refresh" && (!fcmPayload || !fcmPayload.trim())) {
      toast({
        title: "Validation Error",
        description: "Please enter a valid FCM payload",
        variant: "destructive"
      })
      return
    }
    
    if (mode === "shell" && (!shellCommand || !shellCommand.trim())) {
      toast({
        title: "Validation Error",
        description: "Please enter a shell command",
        variant: "destructive"
      })
      return
    }

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
    console.log("[REMOTE-EXEC] Execute button clicked")
    
    let token = getAuthToken()
    console.log("[REMOTE-EXEC] Token check:", token ? "Token found" : "No token")
    
    if (!token) {
      console.error("[REMOTE-EXEC] No auth token - redirecting to login")
      toast({
        title: "Session expired",
        description: "Please sign in again to continue.",
        variant: "destructive"
      })
      router.push("/login")
      return
    }

    console.log("[REMOTE-EXEC] Mode:", mode, "Scope:", scopeType)
    console.log("[REMOTE-EXEC] Preview count:", previewCount)
    console.log("[REMOTE-EXEC] Require confirmation:", requireConfirmation)

    if (requireConfirmation && previewCount && previewCount > 25) {
      const confirmed = confirm(`You are about to execute this command on ${previewCount} devices. Continue?`)
      console.log("[REMOTE-EXEC] User confirmation:", confirmed)
      if (!confirmed) return
    }

    // Re-fetch the token right before executing in case it expired during confirmation
    token = getAuthToken()
    if (!token) {
      console.error("[REMOTE-EXEC] Token expired during confirmation - redirecting to login")
      toast({
        title: "Session expired",
        description: "Please sign in again to continue.",
        variant: "destructive"
      })
      router.push("/login")
      return
    }
    const authToken = token

    // Special handling for soft_update_refresh preset
    if (selectedPreset === "soft_update_refresh" && mode === "fcm") {
      handleSoftUpdateRefresh()
      return
    }
    
    console.log("[REMOTE-EXEC] Starting execution...")
    setIsExecuting(true)
    
    try {
      console.log("[REMOTE-EXEC] Building targets...")
      const targets = buildTargets()
      console.log("[REMOTE-EXEC] Targets built:", JSON.stringify(targets))
      
      const payload = mode === "fcm" ? getFcmPayload() : null
      const command = mode === "shell" ? shellCommand : null
      console.log("[REMOTE-EXEC] Payload/Command:", mode === "fcm" ? payload : command)

      const requestBody = {
        mode,
        targets,
        payload,
        command,
        dry_run: false
      }
      console.log("[REMOTE-EXEC] Request body:", JSON.stringify(requestBody))

      console.log("[REMOTE-EXEC] Sending POST to /api/proxy/v1/remote-exec...")
      const response = await fetch("/api/proxy/v1/remote-exec", {
        method: "POST",
        headers: {
          'Authorization': `Bearer ${authToken}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestBody)
      })

      console.log("[REMOTE-EXEC] Response status:", response.status)

      if (response.status === 401) {
        console.error("[REMOTE-EXEC] 401 Unauthorized - redirecting to login")
        router.push('/login')
        return
      }

      if (response.ok) {
        const data = await response.json()
        console.log("[REMOTE-EXEC] Success response:", data)
        setExecId(data.exec_id)
        setIsPolling(true)
        toast({
          title: "Execution Started",
          description: `Command sent to ${data.sent_count} device(s)`
        })
        fetchRecentExecutions()
      } else {
        const errorText = await response.text()
        console.error("[REMOTE-EXEC] Error response status:", response.status)
        console.error("[REMOTE-EXEC] Error response body:", errorText)
        
        let errorDetail = "Failed to execute command"
        try {
          const error = JSON.parse(errorText)
          errorDetail = error.detail || errorDetail
          console.error("[REMOTE-EXEC] Parsed error detail:", errorDetail)
        } catch (e) {
          console.error("[REMOTE-EXEC] Could not parse error response as JSON")
          errorDetail = errorText || errorDetail
        }
        
        toast({
          title: `Execution Failed (${response.status})`,
          description: errorDetail,
          variant: "destructive"
        })
      }
    } catch (error) {
      console.error("[REMOTE-EXEC] Exception caught:", error)
      if (error instanceof Error) {
        console.error("[REMOTE-EXEC] Error message:", error.message)
        console.error("[REMOTE-EXEC] Error stack:", error.stack)
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
      console.log("[REMOTE-EXEC] Execution finished, resetting state")
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
    setSelectedDeviceIds(filteredDevicesForSelector.map(d => d.id))
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
    // Special handling for soft_update_refresh - it's not a regular FCM preset
    if (presetName === "soft_update_refresh") {
      setSelectedPreset(presetName)
      setFcmPayload("") // Clear FCM payload since this uses a different endpoint
      return
    }
    
    const preset = FCM_PRESETS[presetName as keyof typeof FCM_PRESETS]
    if (preset) {
      setFcmPayload(JSON.stringify(preset, null, 2))
      setSelectedPreset(presetName)
    }
  }

  const applyShellPreset = async (presetName: string) => {
    setSelectedShellPreset(presetName)
    
    if (presetName === "apply_bloatware") {
      const token = getAuthToken()
      if (!token) {
        toast({
          title: "Not authenticated",
          description: "Please sign in again before using presets.",
          variant: "destructive"
        })
        return
      }
      
      try {
        const response = await fetch("/api/proxy/admin/bloatware-list/json", {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        })
        
        if (!response.ok) {
          const error = await response.json().catch(() => ({}))
          throw new Error(error.error || "Failed to fetch disabled apps list")
        }
        
        const data = await response.json()
        const packages: string[] = data.packages?.filter((pkg: any) => pkg.enabled === true).map((pkg: { package_name: string }) => pkg.package_name) ?? []
        
        if (packages.length === 0) {
          toast({
            title: "No packages configured",
            description: "Add packages to the disabled apps list before running this preset.",
            variant: "destructive"
          })
          setShellCommand("")
          return
        }
        
        const command = buildBloatwareDisableCommand(packages)

        setShellCommand(command)
        toast({
          title: "Preset loaded",
          description: `Prepared disable commands for ${packages.length} package${packages.length === 1 ? "" : "s"}.`,
        })
      } catch (error) {
        console.error("Failed to build bloatware command:", error)
        toast({
          title: "Failed to load preset",
          description: error instanceof Error ? error.message : "Unexpected error building command.",
          variant: "destructive"
        })
        setShellCommand("")
        setSelectedShellPreset("")
      }
      
      return
    }
    
    const preset = SHELL_PRESETS[presetName as keyof typeof SHELL_PRESETS]
    if (preset) {
      setShellCommand(preset)
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
                          Select All Filtered ({filteredDevicesForSelector.length})
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

                    <div className="relative">
                      <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
                      <Input
                        placeholder="Filter by device alias (e.g. S, D, Sam...)"
                        value={deviceFilter}
                        onChange={(e) => setDeviceFilter(e.target.value)}
                        className="pl-10"
                      />
                      {deviceFilter && (
                        <div className="mt-2 text-xs text-gray-500">
                          Showing {filteredDevicesForSelector.length} of {allDevices.length} devices
                          {selectedDeviceIds.length > 0 && ` (${selectedDeviceIds.length} selected total)`}
                        </div>
                      )}
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
                      ) : filteredDevicesForSelector.length === 0 ? (
                        <div className="p-8 text-center text-gray-500">
                          No devices match your filter
                        </div>
                      ) : (
                        <div className="divide-y">
                          {filteredDevicesForSelector.map(device => (
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
                          <SelectItem value="launch_unity_app">🚀 Launch Unity App</SelectItem>
                          <SelectItem value="force_stop_unity_app">⛔ Force Stop Unity App</SelectItem>
                          <SelectItem value="launch_app">Launch App (Custom)</SelectItem>
                          <SelectItem value="clear_app_data">Clear App Data</SelectItem>
                          <SelectItem value="enable_dnd">Enable Do Not Disturb (API)</SelectItem>
                          <SelectItem value="disable_dnd">Disable Do Not Disturb (API)</SelectItem>
                          <SelectItem value="exempt_unity_app">🔋 Exempt Unity App from Battery Optimization</SelectItem>
                          <SelectItem value="enable_stay_awake">🔋 Enable Stay Awake When Charging</SelectItem>
                          <SelectItem value="soft_update_refresh">🔄 Soft Update Refresh (Reinstall Unity & Launch)</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="fcmPayload">JSON Payload</Label>
                      <Textarea
                        id="fcmPayload"
                        placeholder='{"type": "ping"}'
                        value={fcmPayload}
                        onChange={(e) => {
                          setFcmPayload(e.target.value)
                          // Clear preset selection on manual edit - user is overriding the preset
                          // For soft_update_refresh, if user types something, they want to use that payload instead
                          if (selectedPreset === "soft_update_refresh" && e.target.value.trim() !== "") {
                            // User is overriding soft_update_refresh with a manual payload
                            setSelectedPreset("")
                          } else if (selectedPreset !== "soft_update_refresh") {
                            // For other presets, always clear on manual edit
                            setSelectedPreset("")
                          }
                        }}
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
                          <SelectItem value="launch_unity_app">🚀 Launch Unity App</SelectItem>
                          <SelectItem value="suppress_wea">Suppress WEA & Enable DND</SelectItem>
                          <SelectItem value="restore_normal">Restore Normal Mode</SelectItem>
                          <SelectItem value="enable_auto_update">✅ Enable Auto-Update Policy</SelectItem>
                          <SelectItem value="disable_auto_update">❌ Disable Auto-Update Policy</SelectItem>
                          <SelectItem value="trigger_update_service">🔄 Trigger System Update Check</SelectItem>
                          <SelectItem value="check_os_version">📱 Check OS Version</SelectItem>
                          <SelectItem value="check_security_patch">🔒 Check Security Patch Level</SelectItem>
                          <SelectItem value="apply_bloatware">🚫 Apply Disabled Apps List</SelectItem>
                          <SelectItem value="enable_stay_awake">🔋 Enable Stay Awake When Charging</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="shellCommand">Shell Command</Label>
                      <Input
                        id="shellCommand"
                        placeholder="am start -n com.minutes.unity/.MainActivity"
                        value={shellCommand}
                        onChange={(e) => {
                          setShellCommand(e.target.value)
                          setSelectedShellPreset("")  // Clear preset selection on manual edit
                        }}
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
                  onClick={(e) => {
                    console.log("[BUTTON] onClick fired", { 
                      disabled: isExecuteDisabled, 
                      isExecuting,
                      mode,
                      selectedPreset,
                      fcmPayloadLength: fcmPayload.length,
                      eventType: e.type
                    })
                    if (!isExecuteDisabled) {
                      e.preventDefault()
                      e.stopPropagation()
                      handleExecute()
                    } else {
                      console.warn("[BUTTON] Button is disabled, not executing", { isExecuteDisabled })
                    }
                  }}
                  disabled={isExecuteDisabled}
                  className="w-full mt-4"
                  type="button"
                  style={{ pointerEvents: isExecuteDisabled ? 'none' : 'auto', cursor: isExecuteDisabled ? 'not-allowed' : 'pointer' }}
                >
                  <Play className="w-4 h-4 mr-2" />
                  {isExecuting ? "Executing..." : "Execute"}
                </Button>

                <div className="mt-6 pt-6 border-t">
                  <Label className="text-sm font-medium mb-3 block">Quick Actions</Label>
                  <div className="flex items-center gap-2">
                    <Input
                      value={restartAppPackage}
                      onChange={(e) => setRestartAppPackage(e.target.value)}
                      placeholder="Package name"
                      className="flex-1 font-mono text-sm"
                    />
                    <Button 
                      onClick={handleRestartApp}
                      disabled={isRestartingApp}
                      variant="secondary"
                      className="whitespace-nowrap"
                    >
                      {isRestartingApp ? "Restarting..." : "🔄 Restart App"}
                    </Button>
                  </div>
                  <p className="text-xs text-gray-500 mt-2">
                    Two-step restart: Force-stop → Launch (uses FCM for reliable launch)
                  </p>
                </div>
              </CardContent>
            </Card>

            {restartAppResults && (
              <Card>
                <CardHeader>
                  <CardTitle>Restart App Results</CardTitle>
                  <CardDescription>
                    Package: {restartAppResults.package_name}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-4 gap-4 mb-6">
                    <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                      <div className="text-2xl font-bold">{restartAppResults.stats?.total || 0}</div>
                      <div className="text-sm text-gray-600 dark:text-gray-400">Total</div>
                    </div>
                    <div className="p-4 bg-green-50 dark:bg-green-900/20 rounded-lg">
                      <div className="text-2xl font-bold">{restartAppResults.stats?.ok || 0}</div>
                      <div className="text-sm text-gray-600 dark:text-gray-400">OK</div>
                    </div>
                    <div className="p-4 bg-red-50 dark:bg-red-900/20 rounded-lg">
                      <div className="text-2xl font-bold">{restartAppResults.stats?.failed || 0}</div>
                      <div className="text-sm text-gray-600 dark:text-gray-400">Failed</div>
                    </div>
                    <div className="p-4 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg">
                      <div className="text-2xl font-bold">{restartAppResults.stats?.pending || 0}</div>
                      <div className="text-sm text-gray-600 dark:text-gray-400">Pending</div>
                    </div>
                  </div>

                  {restartAppResults.devices && restartAppResults.devices.length > 0 && (
                    <div className="border rounded-lg overflow-auto max-h-64">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Alias</TableHead>
                            <TableHead>Force Stop</TableHead>
                            <TableHead>Launch</TableHead>
                            <TableHead>Overall</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {restartAppResults.devices.map((device: any) => (
                            <TableRow key={device.device_id}>
                              <TableCell className="font-medium">{device.alias}</TableCell>
                              <TableCell>
                                <Badge variant={device.force_stop?.status === "OK" ? "default" : device.force_stop?.status === "pending" ? "secondary" : "destructive"}>
                                  {device.force_stop?.status || "N/A"}
                                </Badge>
                              </TableCell>
                              <TableCell>
                                <Badge variant={device.launch?.status === "OK" ? "default" : device.launch?.status === "pending" ? "secondary" : "destructive"}>
                                  {device.launch?.status || "N/A"}
                                </Badge>
                              </TableCell>
                              <TableCell>
                                <Badge variant={device.overall_status === "OK" ? "default" : device.overall_status === "pending" ? "secondary" : "destructive"}>
                                  {device.overall_status}
                                </Badge>
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}

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
                  <>
                    <div className="mb-4">
                      <div className="flex justify-between text-sm mb-2">
                        <span className="font-medium">Progress</span>
                        <span className="text-gray-600">
                          {stats.sent > 0 ? Math.round(((stats.acked + stats.errors) / stats.sent) * 100) : 0}%
                        </span>
                      </div>
                      <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2.5">
                        <div 
                          className="bg-blue-600 h-2.5 rounded-full transition-all duration-300" 
                          style={{ 
                            width: `${stats.sent > 0 ? ((stats.acked + stats.errors) / stats.sent) * 100 : 0}%` 
                          }}
                        />
                      </div>
                    </div>
                    
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
                  </>
                )}

                {sortedResults.length > 0 ? (
                  <>
                    <div className="mb-4">
                      <Input
                        placeholder="Filter by alias or status..."
                        value={resultFilter}
                        onChange={(e) => setResultFilter(e.target.value)}
                        className="max-w-sm"
                      />
                    </div>
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
                          {sortedResults
                            .filter(result => {
                              if (!resultFilter) return true
                              const filter = resultFilter.toLowerCase()
                              return result.alias?.toLowerCase().includes(filter) || 
                                     result.status?.toLowerCase().includes(filter)
                            })
                            .map((result) => (
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
                  </>
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
