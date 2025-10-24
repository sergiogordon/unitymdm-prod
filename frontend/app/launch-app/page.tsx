"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { Header } from "@/components/header"
import { PageHeader } from "@/components/page-header"
import { SettingsDrawer } from "@/components/settings-drawer"
import { Rocket, Play, Eye } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Checkbox } from "@/components/ui/checkbox"
import { Textarea } from "@/components/ui/textarea"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Progress } from "@/components/ui/progress"
import { Badge } from "@/components/ui/badge"
import { useTheme } from "@/contexts/ThemeContext"
import { useToast } from "@/hooks/use-toast"
import { isAuthenticated } from "@/lib/api-client"

interface CommandResult {
  device_id: string
  alias: string
  status: string
  message?: string
  updated_at?: string
}

interface RecentLaunch {
  command_id: string
  package: string
  scope: string
  created_at: string
  stats: {
    total_targets: number
    sent_count: number
    acked_count: number
    error_count: number
  }
}

export default function LaunchAppPage() {
  const router = useRouter()
  const { toast } = useToast()
  const [authChecked, setAuthChecked] = useState(false)
  
  const [packageName, setPackageName] = useState("")
  const [activity, setActivity] = useState("")
  const [wake, setWake] = useState(true)
  const [unlock, setUnlock] = useState(true)
  const [scopeType, setScopeType] = useState<"all" | "filter" | "ids">("all")
  const [deviceIds, setDeviceIds] = useState("")
  const [onlineOnly, setOnlineOnly] = useState(false)
  
  const [isLaunching, setIsLaunching] = useState(false)
  const [isPreviewing, setIsPreviewing] = useState(false)
  const [previewCount, setPreviewCount] = useState<number | null>(null)
  const [previewSample, setPreviewSample] = useState<string[]>([])
  
  const [results, setResults] = useState<CommandResult[]>([])
  const [commandId, setCommandId] = useState<string | null>(null)
  const [progress, setProgress] = useState(0)
  
  const [recentLaunches, setRecentLaunches] = useState<RecentLaunch[]>([])

  // Check authentication
  useEffect(() => {
    if (!isAuthenticated()) {
      router.push('/login')
    } else {
      setAuthChecked(true)
    }
  }, [router])

  useEffect(() => {
    if (authChecked) {
      fetchRecentLaunches()
    }
  }, [authChecked])

  const getAuthToken = (): string | null => {
    if (typeof window === 'undefined') return null
    return localStorage.getItem('auth_token')
  }

  const fetchRecentLaunches = async () => {
    try {
      const token = getAuthToken()
      if (!token) return

      const response = await fetch("/api/proxy/v1/commands?type=launch_app&limit=3", {
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
        setRecentLaunches(data.commands || [])
      }
    } catch (error) {
      console.error("Failed to fetch recent launches:", error)
    }
  }

  const buildTargets = () => {
    if (scopeType === "all") {
      return { all: true }
    } else if (scopeType === "filter") {
      return {
        filter: {
          online: onlineOnly || undefined
        }
      }
    } else {
      const ids = deviceIds.split(/[\s,\n]+/).filter(id => id.trim())
      return { device_ids: ids }
    }
  }

  const handlePreview = async () => {
    if (!packageName.trim()) {
      toast({
        title: "Validation Error",
        description: "Package name is required",
        variant: "destructive"
      })
      return
    }

    const token = getAuthToken()
    if (!token) {
      router.push('/login')
      return
    }

    setIsPreviewing(true)
    setPreviewCount(null)
    setPreviewSample([])

    try {
      const response = await fetch("/api/proxy/v1/commands/launch_app", {
        method: "POST",
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          targets: buildTargets(),
          command: {
            package: packageName,
            activity: activity || undefined,
            wake,
            unlock,
            correlation_id: crypto.randomUUID()
          },
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
        setPreviewSample(data.sample_device_ids || [])
        toast({
          title: "Preview Complete",
          description: `Will target ${data.estimated_count} device(s)`,
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
      toast({
        title: "Error",
        description: "Failed to preview targets",
        variant: "destructive"
      })
    } finally {
      setIsPreviewing(false)
    }
  }

  const handleLaunch = async () => {
    if (!packageName.trim()) {
      toast({
        title: "Validation Error",
        description: "Package name is required",
        variant: "destructive"
      })
      return
    }

    const token = getAuthToken()
    if (!token) {
      router.push('/login')
      return
    }

    setIsLaunching(true)
    setResults([])
    setCommandId(null)
    setProgress(0)

    try {
      const response = await fetch("/api/proxy/v1/commands/launch_app", {
        method: "POST",
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          targets: buildTargets(),
          command: {
            package: packageName,
            activity: activity || undefined,
            wake,
            unlock,
            correlation_id: crypto.randomUUID()
          },
          dry_run: false
        })
      })

      if (response.status === 401) {
        router.push('/login')
        return
      }

      if (response.ok) {
        const data = await response.json()
        setCommandId(data.command_id)
        setProgress(50)
        
        toast({
          title: "Launch Initiated",
          description: `Commands sent to ${data.total_targets} device(s)`,
        })
        
        pollCommandStatus(data.command_id)
        fetchRecentLaunches()
      } else {
        const error = await response.json()
        toast({
          title: "Launch Failed",
          description: error.detail || "Failed to launch app",
          variant: "destructive"
        })
      }
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to launch app",
        variant: "destructive"
      })
    } finally {
      setIsLaunching(false)
    }
  }

  const pollCommandStatus = async (cmdId: string) => {
    const poll = async () => {
      try {
        const token = getAuthToken()
        if (!token) return

        const response = await fetch(`/api/proxy/v1/commands/${cmdId}`, {
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
          setResults(data.results || [])
          
          const totalTargets = data.stats.total_targets || 1
          const acked = data.stats.acked_count || 0
          setProgress(Math.round((acked / totalTargets) * 100))
          
          if (data.status === "completed") {
            toast({
              title: "Launch Complete",
              description: `${data.stats.acked_count}/${totalTargets} devices acknowledged`,
            })
            return
          }
          
          setTimeout(poll, 2000)
        }
      } catch (error) {
        console.error("Polling error:", error)
      }
    }
    
    poll()
  }

  const getStatusBadge = (status: string) => {
    const statusMap: Record<string, { variant: any; label: string }> = {
      sent: { variant: "default", label: "Sent" },
      OK: { variant: "default", label: "Success" },
      ok: { variant: "default", label: "Success" },
      NOT_INSTALLED: { variant: "destructive", label: "Not Installed" },
      ACTIVITY_NOT_FOUND: { variant: "destructive", label: "Activity Not Found" },
      SECURITY_ERROR: { variant: "destructive", label: "Security Error" },
      TIMEOUT: { variant: "destructive", label: "Timeout" },
      FAILED: { variant: "destructive", label: "Failed" },
      failed: { variant: "destructive", label: "Failed" }
    }
    
    const config = statusMap[status] || { variant: "secondary", label: status }
    return <Badge variant={config.variant}>{config.label}</Badge>
  }

  if (!authChecked) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gray-900 dark:border-gray-100 mx-auto mb-4"></div>
          <p className="text-muted-foreground">Checking authentication...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen">
      <Header />

      <main className="mx-auto max-w-[1600px] px-6 pb-12 pt-[84px] md:px-8">
        <PageHeader
          icon={<Rocket className="h-8 w-8" />}
          title="Launch App"
          description="Remotely launch applications on managed devices."
        />

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <Card className="rounded-2xl border border-border bg-card p-6 shadow-sm">
              <h2 className="text-xl font-semibold mb-4">Launch Configuration</h2>
              
              <div className="space-y-4">
                <div>
                  <Label htmlFor="package">App Package *</Label>
                  <Input
                    id="package"
                    placeholder="com.example.app"
                    value={packageName}
                    onChange={(e) => setPackageName(e.target.value)}
                    className="mt-1"
                  />
                </div>

                <div>
                  <Label htmlFor="activity">Activity (optional)</Label>
                  <Input
                    id="activity"
                    placeholder=".MainActivity"
                    value={activity}
                    onChange={(e) => setActivity(e.target.value)}
                    className="mt-1"
                  />
                </div>

                <div className="flex gap-6">
                  <div className="flex items-center space-x-2">
                    <Checkbox
                      id="wake"
                      checked={wake}
                      onCheckedChange={(checked) => setWake(checked as boolean)}
                    />
                    <Label htmlFor="wake" className="font-normal cursor-pointer">
                      Wake screen
                    </Label>
                  </div>

                  <div className="flex items-center space-x-2">
                    <Checkbox
                      id="unlock"
                      checked={unlock}
                      onCheckedChange={(checked) => setUnlock(checked as boolean)}
                    />
                    <Label htmlFor="unlock" className="font-normal cursor-pointer">
                      Unlock if possible (Device Owner)
                    </Label>
                  </div>
                </div>

                <div>
                  <Label className="mb-2 block">Scope</Label>
                  <Tabs value={scopeType} onValueChange={(v) => setScopeType(v as any)}>
                    <TabsList className="grid w-full grid-cols-3">
                      <TabsTrigger value="all">Entire Fleet</TabsTrigger>
                      <TabsTrigger value="filter">Filtered Set</TabsTrigger>
                      <TabsTrigger value="ids">Device IDs</TabsTrigger>
                    </TabsList>
                    
                    <TabsContent value="all" className="mt-4">
                      <p className="text-sm text-muted-foreground">
                        Launch on all devices with FCM tokens registered.
                      </p>
                    </TabsContent>
                    
                    <TabsContent value="filter" className="mt-4 space-y-3">
                      <div className="flex items-center space-x-2">
                        <Checkbox
                          id="online"
                          checked={onlineOnly}
                          onCheckedChange={(checked) => setOnlineOnly(checked as boolean)}
                        />
                        <Label htmlFor="online" className="font-normal cursor-pointer">
                          Online devices only (seen in last 10 minutes)
                        </Label>
                      </div>
                    </TabsContent>
                    
                    <TabsContent value="ids" className="mt-4">
                      <Textarea
                        placeholder="Enter device IDs (comma, space, or line separated)"
                        value={deviceIds}
                        onChange={(e) => setDeviceIds(e.target.value)}
                        rows={4}
                      />
                    </TabsContent>
                  </Tabs>
                </div>

                <div className="flex gap-3 pt-4">
                  <Button
                    variant="outline"
                    onClick={handlePreview}
                    disabled={isPreviewing || isLaunching}
                  >
                    <Eye className="h-4 w-4 mr-2" />
                    Preview Targets
                  </Button>
                  
                  <Button
                    onClick={handleLaunch}
                    disabled={isLaunching || isPreviewing}
                  >
                    <Play className="h-4 w-4 mr-2" />
                    {isLaunching ? "Launching..." : "Launch"}
                  </Button>
                </div>

                {previewCount !== null && (
                  <div className="p-4 bg-muted rounded-lg">
                    <p className="font-medium">Preview: {previewCount} device(s)</p>
                    {previewSample.length > 0 && (
                      <p className="text-sm text-muted-foreground mt-1">
                        Sample: {previewSample.slice(0, 5).join(", ")}
                        {previewSample.length > 5 && "..."}
                      </p>
                    )}
                  </div>
                )}
              </div>
            </Card>

            {commandId && (
              <Card className="rounded-2xl border border-border bg-card p-6 shadow-sm">
                <h2 className="text-xl font-semibold mb-4">Execution Results</h2>
                
                <div className="space-y-4">
                  <div>
                    <div className="flex justify-between text-sm mb-2">
                      <span>Progress</span>
                      <span>{progress}%</span>
                    </div>
                    <Progress value={progress} className="h-2" />
                  </div>

                  {results.length > 0 && (
                    <div className="border rounded-lg overflow-hidden">
                      <table className="w-full">
                        <thead className="bg-muted">
                          <tr>
                            <th className="px-4 py-2 text-left text-sm font-medium">Device ID</th>
                            <th className="px-4 py-2 text-left text-sm font-medium">Alias</th>
                            <th className="px-4 py-2 text-left text-sm font-medium">Status</th>
                            <th className="px-4 py-2 text-left text-sm font-medium">Message</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y">
                          {results.map((result) => (
                            <tr key={result.device_id}>
                              <td className="px-4 py-2 text-sm font-mono">{result.device_id}</td>
                              <td className="px-4 py-2 text-sm">{result.alias}</td>
                              <td className="px-4 py-2 text-sm">{getStatusBadge(result.status)}</td>
                              <td className="px-4 py-2 text-sm text-muted-foreground">
                                {result.message || "-"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </Card>
            )}
          </div>

          <div className="lg:col-span-1">
            <Card className="rounded-2xl border border-border bg-card p-6 shadow-sm sticky top-24">
              <h2 className="text-xl font-semibold mb-4">Recent Launches</h2>
              
              {recentLaunches.length === 0 ? (
                <p className="text-sm text-muted-foreground">No recent launches</p>
              ) : (
                <div className="space-y-3">
                  {recentLaunches.map((launch) => (
                    <div
                      key={launch.command_id}
                      className="p-3 border rounded-lg hover:bg-muted/50 transition-colors cursor-pointer"
                      onClick={() => {
                        setCommandId(launch.command_id)
                        pollCommandStatus(launch.command_id)
                      }}
                    >
                      <div className="flex items-start justify-between mb-2">
                        <p className="font-medium text-sm truncate flex-1">{launch.package}</p>
                        <Badge variant="outline" className="ml-2 text-xs">
                          {launch.scope}
                        </Badge>
                      </div>
                      
                      <div className="flex gap-4 text-xs text-muted-foreground mb-1">
                        <span>✓ {launch.stats.acked_count}</span>
                        <span>✗ {launch.stats.error_count}</span>
                        <span>Total: {launch.stats.total_targets}</span>
                      </div>
                      
                      <p className="text-xs text-muted-foreground">
                        {new Date(launch.created_at).toLocaleString()}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>
        </div>
      </main>
    </div>
  )
}
