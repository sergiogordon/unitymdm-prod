"use client"
import { ProtectedLayout } from "@/components/protected-layout"
import { useState, useEffect } from "react"
import { Copy, Check, Terminal, Download, Eye, EyeOff, RefreshCw, ChevronDown, ChevronUp, FileCode, Command } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Header } from "@/components/header"
import { SettingsDrawer } from "@/components/settings-drawer"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"

interface EnrollmentToken {
  token_id: string
  alias: string
  token_last4: string
  status: string
  expires_at: string
  uses_allowed: number
  uses_consumed: number
  note: string | null
  issued_at: string
  issued_by: string | null
  full_token?: string
}

export default function ADBSetupPage() {
  return (
    <ProtectedLayout>
      <ADBSetupContent />
    </ProtectedLayout>
  )
}

function ADBSetupContent() {
  const [aliases, setAliases] = useState("")
  const [expiryMinutes, setExpiryMinutes] = useState("30")
  const [note, setNote] = useState("")
  const [loading, setLoading] = useState(false)
  const [tokens, setTokens] = useState<EnrollmentToken[]>([])
  const [revealedTokens, setRevealedTokens] = useState<Set<string>>(new Set())
  const [expandedScripts, setExpandedScripts] = useState<Set<string>>(new Set())
  const [scriptContents, setScriptContents] = useState<Record<string, { bash: string, windows: string }>>({})
  const [isDark, setIsDark] = useState(false)
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)

  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add("dark")
    } else {
      document.documentElement.classList.remove("dark")
    }
  }, [isDark])

  useEffect(() => {
    const isDarkMode = localStorage.getItem('darkMode') === 'true'
    setIsDark(isDarkMode)
  }, [])

  useEffect(() => {
    fetchTokens()
  }, [])

  const fetchTokens = async () => {
    try {
      const token = localStorage.getItem('auth_token')
      const response = await fetch("/api/proxy/v1/enroll-tokens?limit=50", {
        headers: {
          "Authorization": `Bearer ${token}`
        }
      })
      
      if (response.ok) {
        const data = await response.json()
        setTokens(data.tokens || [])
      }
    } catch (error) {
      console.error("Failed to fetch tokens:", error)
    }
  }

  const generateTokens = async () => {
    if (!aliases.trim()) {
      alert("Please enter at least one alias")
      return
    }

    setLoading(true)
    try {
      const aliasArray = aliases.split(/[,\s]+/).filter(a => a.trim())
      const token = localStorage.getItem('auth_token')
      
      const response = await fetch("/api/proxy/v1/enroll-tokens", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`
        },
        body: JSON.stringify({
          aliases: aliasArray,
          expires_in_sec: parseInt(expiryMinutes) * 60,
          uses_allowed: 1,
          note: note.trim() || null
        }),
      })
      
      if (!response.ok) {
        throw new Error("Failed to generate tokens")
      }
      
      const data = await response.json()
      
      const newTokens = data.tokens.map((t: any) => ({
        token_id: t.token_id,
        alias: t.alias,
        token_last4: t.token.slice(-4),
        status: 'active',
        expires_at: t.expires_at,
        uses_allowed: 1,
        uses_consumed: 0,
        note: note.trim() || null,
        issued_at: new Date().toISOString(),
        issued_by: null,
        full_token: t.token
      }))
      
      setTokens([...newTokens, ...tokens])
      setAliases("")
      setNote("")
    } catch (error) {
      alert("Failed to generate tokens. Please try again.")
      console.error(error)
    } finally {
      setLoading(false)
    }
  }

  const toggleTokenReveal = (tokenId: string) => {
    const newRevealed = new Set(revealedTokens)
    if (newRevealed.has(tokenId)) {
      newRevealed.delete(tokenId)
    } else {
      newRevealed.add(tokenId)
    }
    setRevealedTokens(newRevealed)
  }

  const copyToken = async (token: EnrollmentToken) => {
    if (token.full_token) {
      await navigator.clipboard.writeText(token.full_token)
      alert("Token copied to clipboard!")
    } else {
      alert("Token value not available. Only newly generated tokens can be copied.")
    }
  }

  const fetchScriptContent = async (token: EnrollmentToken) => {
    const authToken = localStorage.getItem('auth_token')
    
    setScriptContents(prev => ({
      ...prev,
      [token.token_id]: {
        bash: 'Loading...',
        windows: 'Loading...'
      }
    }))
    
    try {
      const [bashResponse, windowsResponse] = await Promise.all([
        fetch(`/api/proxy/v1/scripts/enroll.sh?alias=${encodeURIComponent(token.alias)}&token_id=${encodeURIComponent(token.token_id)}&agent_pkg=com.nexmdm&unity_pkg=org.zwanoo.android.speedtest`, {
          headers: { "Authorization": `Bearer ${authToken}` }
        }),
        fetch(`/api/proxy/v1/scripts/enroll.cmd?alias=${encodeURIComponent(token.alias)}&token_id=${encodeURIComponent(token.token_id)}&agent_pkg=com.nexmdm&unity_pkg=org.zwanoo.android.speedtest`, {
          headers: { "Authorization": `Bearer ${authToken}` }
        })
      ])

      if (!bashResponse.ok || !windowsResponse.ok) {
        throw new Error('Failed to fetch scripts')
      }

      const bashText = await bashResponse.text()
      const windowsText = await windowsResponse.text()

      setScriptContents(prev => ({
        ...prev,
        [token.token_id]: {
          bash: bashText,
          windows: windowsText
        }
      }))
    } catch (error) {
      console.error("Failed to fetch script content:", error)
      setScriptContents(prev => ({
        ...prev,
        [token.token_id]: {
          bash: 'Error loading script. Please try downloading instead.',
          windows: 'Error loading script. Please try downloading instead.'
        }
      }))
    }
  }

  const toggleScriptExpand = (token: EnrollmentToken) => {
    setExpandedScripts(prev => {
      const newExpanded = new Set(prev)
      if (newExpanded.has(token.token_id)) {
        newExpanded.delete(token.token_id)
      } else {
        newExpanded.add(token.token_id)
        if (!scriptContents[token.token_id]) {
          fetchScriptContent(token)
        }
      }
      return newExpanded
    })
  }

  const downloadScript = async (token: EnrollmentToken, platform: 'windows' | 'bash') => {
    const authToken = localStorage.getItem('auth_token')
    const endpoint = platform === 'windows' ? '/api/proxy/v1/scripts/enroll.cmd' : '/api/proxy/v1/scripts/enroll.sh'
    const url = `${endpoint}?alias=${encodeURIComponent(token.alias)}&token_id=${encodeURIComponent(token.token_id)}&agent_pkg=com.nexmdm&unity_pkg=org.zwanoo.android.speedtest`
    
    try {
      const response = await fetch(url, {
        headers: {
          "Authorization": `Bearer ${authToken}`
        }
      })
      
      if (!response.ok) {
        throw new Error("Failed to download script")
      }
      
      const blob = await response.blob()
      const downloadUrl = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = downloadUrl
      a.download = `enroll-${token.alias}.${platform === 'windows' ? 'cmd' : 'sh'}`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(downloadUrl)
      document.body.removeChild(a)
    } catch (error) {
      alert(`Failed to download ${platform} script`)
      console.error(error)
    }
  }

  const copyOneLiner = async (token: EnrollmentToken) => {
    const authToken = localStorage.getItem('auth_token')
    const url = `/api/proxy/v1/scripts/enroll.one-liner.cmd?alias=${encodeURIComponent(token.alias)}&token_id=${encodeURIComponent(token.token_id)}&agent_pkg=com.nexmdm&unity_pkg=org.zwanoo.android.speedtest`
    
    try {
      const response = await fetch(url, {
        headers: {
          "Authorization": `Bearer ${authToken}`
        }
      })
      
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(errorText || "Failed to fetch one-liner")
      }
      
      const oneLinerCommand = await response.text()
      await navigator.clipboard.writeText(oneLinerCommand)
      alert(`✅ One-liner copied to clipboard!\n\nPaste into Windows Command Prompt (cmd.exe) to enroll device "${token.alias}"`)
    } catch (error) {
      alert(`Failed to copy one-liner: ${error}`)
      console.error(error)
    }
  }

  const copyScriptToClipboard = async (scriptContent: string, platform: string) => {
    try {
      await navigator.clipboard.writeText(scriptContent)
      alert(`${platform} script copied to clipboard!`)
    } catch (error) {
      console.error("Failed to copy:", error)
      alert("Failed to copy script to clipboard")
    }
  }

  const getStatusBadge = (status: string) => {
    const variants: Record<string, { variant: any, label: string }> = {
      'active': { variant: 'default', label: 'Active' },
      'exhausted': { variant: 'secondary', label: 'Exhausted' },
      'expired': { variant: 'destructive', label: 'Expired' },
      'revoked': { variant: 'outline', label: 'Revoked' }
    }
    
    const config = variants[status] || variants['active']
    return <Badge variant={config.variant}>{config.label}</Badge>
  }

  const formatDateTime = (dateStr: string) => {
    const date = new Date(dateStr)
    return date.toLocaleString()
  }

  const handleToggleDark = () => {
    const newDarkMode = !isDark
    setIsDark(newDarkMode)
    localStorage.setItem('darkMode', String(newDarkMode))
  }

  return (
    <div className="min-h-screen">
      <Header 
        lastUpdated={Date.now()} 
        alertCount={0} 
        isDark={isDark} 
        onToggleDark={handleToggleDark}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onRefresh={() => {}}
      />
      
      <main className="mx-auto max-w-[1280px] space-y-6 px-6 pb-12 pt-[84px] md:px-8">
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <Terminal className="h-6 w-6" />
            <h1 className="text-3xl font-bold tracking-tight">ADB Setup</h1>
          </div>
          <p className="text-muted-foreground">
            Generate per-device tokens and one-click ADB scripts. Each script downloads the latest APK, grants required permissions, applies optimizations, and auto-registers the device—typically visible in the dashboard within ~60 seconds.
          </p>
        </div>

        <div className="rounded-lg border bg-card p-6 shadow-sm">
          <h2 className="text-lg font-semibold mb-4">Token Generator</h2>
          <div className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="aliases">Device Aliases</Label>
                <Input
                  id="aliases"
                  placeholder="e.g., D01, D02, D03 or Device-01 Device-02"
                  value={aliases}
                  onChange={(e) => setAliases(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  Comma or space separated. Supports batch generation.
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="expiry">Token Expiry</Label>
                <Select value={expiryMinutes} onValueChange={setExpiryMinutes}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="15">15 minutes</SelectItem>
                    <SelectItem value="30">30 minutes</SelectItem>
                    <SelectItem value="60">60 minutes</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="note">Note (Optional)</Label>
              <Input
                id="note"
                placeholder="e.g., Oct-ops batch A"
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
            </div>

            <Button onClick={generateTokens} disabled={loading || !aliases.trim()}>
              {loading ? "Generating..." : "Generate Tokens"}
            </Button>
          </div>
        </div>

        {tokens.length > 0 && (
          <div className="rounded-lg border bg-card p-6 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">Enrollment Tokens</h2>
              <Button
                variant="outline"
                size="sm"
                onClick={fetchTokens}
                className="gap-2"
              >
                <RefreshCw className="h-4 w-4" />
                Refresh
              </Button>
            </div>
            
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Alias</TableHead>
                    <TableHead>Token</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Expires</TableHead>
                    <TableHead>Uses</TableHead>
                    <TableHead>Note</TableHead>
                    <TableHead>Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {tokens.map((token) => (
                    <>
                      <TableRow key={token.token_id}>
                        <TableCell className="font-medium">{token.alias}</TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <code className="text-xs">
                              {revealedTokens.has(token.token_id) && token.full_token
                                ? token.full_token
                                : `****${token.token_last4}`}
                            </code>
                            {token.full_token && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => toggleTokenReveal(token.token_id)}
                              >
                                {revealedTokens.has(token.token_id) ? (
                                  <EyeOff className="h-3 w-3" />
                                ) : (
                                  <Eye className="h-3 w-3" />
                                )}
                              </Button>
                            )}
                          </div>
                        </TableCell>
                        <TableCell>{getStatusBadge(token.status)}</TableCell>
                        <TableCell className="text-xs">{formatDateTime(token.expires_at)}</TableCell>
                        <TableCell className="text-xs">{token.uses_consumed}/{token.uses_allowed}</TableCell>
                        <TableCell className="text-xs">{token.note || '-'}</TableCell>
                        <TableCell>
                          <div className="flex gap-2 flex-wrap">
                            <Button
                              variant="default"
                              size="sm"
                              onClick={() => copyOneLiner(token)}
                              title="Copy One-Liner (Windows CMD) - Paste into Command Prompt. Requires ADB in PATH."
                              disabled={token.status !== 'active'}
                              className="gap-1"
                            >
                              <Command className="h-3 w-3" />
                              One-Liner
                            </Button>
                            {token.full_token && (
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => copyToken(token)}
                                title="Copy Token"
                              >
                                <Copy className="h-3 w-3" />
                              </Button>
                            )}
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => downloadScript(token, 'windows')}
                              title="Download Windows Script"
                            >
                              <Download className="h-3 w-3 mr-1" />
                              .cmd
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => downloadScript(token, 'bash')}
                              title="Download Bash Script"
                            >
                              <Download className="h-3 w-3 mr-1" />
                              .sh
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => toggleScriptExpand(token)}
                              title="View Script Contents"
                            >
                              {expandedScripts.has(token.token_id) ? (
                                <ChevronUp className="h-3 w-3" />
                              ) : (
                                <ChevronDown className="h-3 w-3" />
                              )}
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                      {expandedScripts.has(token.token_id) && (
                        <TableRow>
                          <TableCell colSpan={7} className="bg-muted/30 p-4">
                            <div className="space-y-4">
                              <div className="flex items-center gap-2 mb-2">
                                <FileCode className="h-4 w-4" />
                                <h4 className="font-semibold">Enrollment Scripts Preview</h4>
                              </div>
                              
                              {scriptContents[token.token_id] ? (
                                <div className="space-y-4">
                                  <div>
                                    <div className="flex items-center justify-between mb-2">
                                      <Label className="text-sm font-medium">Bash Script (.sh)</Label>
                                      <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={() => copyScriptToClipboard(scriptContents[token.token_id].bash, 'Bash')}
                                      >
                                        <Copy className="h-3 w-3 mr-1" />
                                        Copy
                                      </Button>
                                    </div>
                                    <pre className="bg-background border rounded-md p-4 overflow-x-auto text-xs max-h-96">
                                      <code>{scriptContents[token.token_id].bash}</code>
                                    </pre>
                                  </div>
                                  
                                  <div>
                                    <div className="flex items-center justify-between mb-2">
                                      <Label className="text-sm font-medium">Windows Script (.cmd)</Label>
                                      <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={() => copyScriptToClipboard(scriptContents[token.token_id].windows, 'Windows')}
                                      >
                                        <Copy className="h-3 w-3 mr-1" />
                                        Copy
                                      </Button>
                                    </div>
                                    <pre className="bg-background border rounded-md p-4 overflow-x-auto text-xs max-h-96">
                                      <code>{scriptContents[token.token_id].windows}</code>
                                    </pre>
                                  </div>
                                </div>
                              ) : (
                                <div className="text-sm text-muted-foreground">Loading scripts...</div>
                              )}
                            </div>
                          </TableCell>
                        </TableRow>
                      )}
                    </>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        )}

        <div className="rounded-md border border-blue-500/50 bg-blue-500/10 p-4">
          <h3 className="font-semibold text-blue-700 dark:text-blue-300 mb-2">Enrollment Checklist</h3>
          <ul className="list-disc list-inside space-y-1 text-sm text-muted-foreground">
            <li>Enable USB debugging on device</li>
            <li>Trust host computer when prompted</li>
            <li>Factory reset only if using Device Owner mode (optional but recommended)</li>
            <li>Device Owner set only succeeds on factory-reset devices—safe to leave enabled</li>
          </ul>
        </div>
      </main>

      <SettingsDrawer
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
      />
    </div>
  )
}
