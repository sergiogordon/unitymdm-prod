"use client"

import { useState, useEffect, useRef } from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { 
  CheckCircle2, 
  XCircle, 
  Loader2, 
  Copy, 
  Check,
  ArrowRight,
  ArrowLeft,
  Key,
  Shield,
  Cloud,
  Github,
  Settings,
  Sparkles,
  AlertCircle,
  Info,
  Database,
  Mail
} from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { Checkbox } from "@/components/ui/checkbox"
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { ChevronDown, ExternalLink, HelpCircle } from "lucide-react"
import { checkBackendHealth, pollBackendHealth, type BackendHealthStatus } from "@/lib/backend-health"

interface SetupStatus {
  required: {
    admin_key: { configured: boolean; valid: boolean; message: string }
    jwt_secret: { configured: boolean; valid: boolean; message: string }
    hmac_secret: { configured: boolean; valid: boolean; message: string }
    firebase: { configured: boolean; valid: boolean; message: string }
    database: { 
      configured: boolean
      valid: boolean
      message: string
      type: string | null
      connection_tested: boolean
    }
  }
  optional: {
    discord_webhook: { configured: boolean; message: string }
    github_ci: { configured: boolean; message: string }
    object_storage: { configured: boolean; available: boolean; message: string }
    email_service: { configured: boolean; available: boolean; message: string }
  }
  ready: boolean
}

const BACKEND_URL = '/api/proxy'

export default function SetupPage() {
  const router = useRouter()
  const [currentStep, setCurrentStep] = useState(0)
  const [status, setStatus] = useState<SetupStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [checking, setChecking] = useState(false)
  const [backendError, setBackendError] = useState<string | null>(null)
  
  // Backend health status
  const [backendHealth, setBackendHealth] = useState<BackendHealthStatus | null>(null)
  const [checkingBackend, setCheckingBackend] = useState(false)
  const [pollingBackend, setPollingBackend] = useState(false)
  const pollingRef = useRef<boolean>(false)
  const pollingCancelRef = useRef<(() => void) | null>(null)
  
  // Database test status
  const [testingDatabase, setTestingDatabase] = useState(false)
  const [databaseTestResult, setDatabaseTestResult] = useState<{ connected: boolean; message: string; type?: string } | null>(null)
  
  // End-to-end verification status
  const [verifying, setVerifying] = useState(false)
  const [verificationResult, setVerificationResult] = useState<{
    backend: { available: boolean; message: string }
    database: { available: boolean; message: string }
    object_storage: { available: boolean; message: string }
    signup_endpoint: { available: boolean; message: string }
    all_ready: boolean
  } | null>(null)
  
  // Step 1: Admin Credentials
  const [adminKey, setAdminKey] = useState("")
  const [jwtSecret, setJwtSecret] = useState("")
  const [hmacSecret, setHmacSecret] = useState("")
  const [copied, setCopied] = useState<string | null>(null)
  
  // Database configuration
  const [databaseUrl, setDatabaseUrl] = useState("")
  const [databaseType, setDatabaseType] = useState<"sqlite" | "postgresql" | "manual">("sqlite")
  const [usePostgresParams, setUsePostgresParams] = useState(false)
  const [pgHost, setPgHost] = useState("")
  const [pgPort, setPgPort] = useState("5432")
  const [pgUser, setPgUser] = useState("")
  const [pgPassword, setPgPassword] = useState("")
  const [pgDatabase, setPgDatabase] = useState("")
  
  // Discord webhook
  const [discordWebhookUrl, setDiscordWebhookUrl] = useState("")
  
  // Step 2: Firebase
  const [firebaseJson, setFirebaseJson] = useState("")
  const [firebaseValidating, setFirebaseValidating] = useState(false)
  const [firebaseValid, setFirebaseValid] = useState<boolean | null>(null)
  const [firebaseMessage, setFirebaseMessage] = useState("")
  
  // Step 3: GitHub CI (recommended)
  const [showGitHub, setShowGitHub] = useState(false)
  const [skipGitHubCI, setSkipGitHubCI] = useState(false)
  const [githubRepo, setGithubRepo] = useState("")
  
  // Step 4: Keystore (optional)
  const [keystorePassword, setKeystorePassword] = useState("")
  const [keyPassword, setKeyPassword] = useState("")
  const [keyAlias, setKeyAlias] = useState("nexmdm")

  // Define steps array before useEffect that references it
  const steps = [
    {
      id: 'welcome',
      title: 'Welcome to NexMDM Setup',
      icon: Sparkles
    },
    {
      id: 'admin',
      title: 'Admin Credentials',
      icon: Key
    },
    {
      id: 'firebase',
      title: 'Firebase Configuration',
      icon: Cloud
    },
    {
      id: 'database',
      title: 'Database Configuration',
      icon: Database
    },
    {
      id: 'github',
      title: 'GitHub CI/CD (Recommended)',
      icon: Github
    },
    {
      id: 'discord',
      title: 'Discord Webhook (Optional)',
      icon: Mail
    },
    {
      id: 'keystore',
      title: 'Android Keystore (Optional)',
      icon: Shield
    },
    {
      id: 'complete',
      title: 'Setup Complete',
      icon: CheckCircle2
    }
  ]

  // Load saved progress from localStorage
  useEffect(() => {
    const savedStep = localStorage.getItem('setup_step')
    if (savedStep) {
      const step = parseInt(savedStep, 10)
      if (step >= 0 && step < steps.length) {
        setCurrentStep(step)
      }
    }
  }, [steps.length])

  useEffect(() => {
    checkSetupStatus()
  }, [])

  // Check backend health when completion step is shown
  useEffect(() => {
    if (currentStep === 7) { // Complete step is now step 7
      checkBackendHealthStatus()
    } else {
      // Reset backend health when leaving completion step
      setBackendHealth(null)
      pollingRef.current = false
      setPollingBackend(false)
      // Cancel any active polling
      if (pollingCancelRef.current) {
        pollingCancelRef.current()
        pollingCancelRef.current = null
      }
    }
    
    return () => {
      // Cleanup: stop polling when component unmounts or step changes
      pollingRef.current = false
      setPollingBackend(false)
      // Cancel any active polling
      if (pollingCancelRef.current) {
        pollingCancelRef.current()
        pollingCancelRef.current = null
      }
    }
  }, [currentStep])

  const checkBackendHealthStatus = async () => {
    setCheckingBackend(true)
    try {
      const health = await checkBackendHealth(true, 5000)
      setBackendHealth(health)
      
      // If backend is not running, start polling
      if (health.status === 'not_running' && !pollingBackend) {
        startBackendPolling()
      }
    } catch (error) {
      console.error('Failed to check backend health:', error)
      setBackendHealth({
        status: 'error',
        message: 'Failed to check backend health',
        error: error instanceof Error ? error.message : 'unknown',
      })
    } finally {
      setCheckingBackend(false)
    }
  }

  const startBackendPolling = async () => {
    if (pollingBackend || pollingRef.current) return
    
    pollingRef.current = true
    setPollingBackend(true)
    
    // Cancel any existing polling
    if (pollingCancelRef.current) {
      pollingCancelRef.current()
      pollingCancelRef.current = null
    }
    
    try {
      const { promise, cancel } = pollBackendHealth(
        (status) => {
          if (!pollingRef.current) return // Stop if cancelled
          
          setBackendHealth(status)
          if (status.status === 'running') {
            pollingRef.current = false
            setPollingBackend(false)
            pollingCancelRef.current = null
            toast.success('Backend server is now running!')
          }
        },
        5000, // Poll every 5 seconds
        12, // Max 12 attempts (60 seconds total)
        true // Use proxy
      )
      
      pollingCancelRef.current = cancel
      
      await promise
    } catch (error) {
      console.error('Backend polling error:', error)
    } finally {
      if (pollingRef.current) {
        pollingRef.current = false
        setPollingBackend(false)
        if (pollingCancelRef.current) {
          pollingCancelRef.current()
          pollingCancelRef.current = null
        }
      }
    }
  }

  const testDatabaseConnection = async () => {
    setTestingDatabase(true)
    setDatabaseTestResult(null)
    try {
      const response = await fetch(`${BACKEND_URL}/api/setup/test-database`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      })

      const data = await response.json()

      if (response.ok) {
        setDatabaseTestResult({
          connected: data.connected,
          message: data.message,
          type: data.type,
        })
        
        if (data.connected) {
          toast.success('Database connection successful!')
          // Refresh setup status to get updated database info
          await checkSetupStatus()
        } else {
          toast.error(`Database connection failed: ${data.message}`)
        }
      } else {
        setDatabaseTestResult({
          connected: false,
          message: data.message || data.detail || 'Failed to test database connection',
        })
        toast.error('Failed to test database connection')
      }
    } catch (error) {
      console.error('Database test error:', error)
      setDatabaseTestResult({
        connected: false,
        message: error instanceof Error ? error.message : 'Network error - backend may not be running',
      })
      toast.error('Failed to test database connection')
    } finally {
      setTestingDatabase(false)
    }
  }

  const verifyEverything = async () => {
    setVerifying(true)
    setVerificationResult(null)
    try {
      const response = await fetch(`${BACKEND_URL}/api/setup/verify`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      })

      const data = await response.json()

      if (response.ok) {
        setVerificationResult(data)
        
        if (data.all_ready) {
          toast.success('All systems ready! You can proceed to signup.')
        } else {
          const issues = []
          if (!data.backend.available) issues.push('Backend')
          if (!data.database.available) issues.push('Database')
          if (!data.object_storage.available) issues.push('Object Storage')
          toast.warning(`Some components need attention: ${issues.join(', ')}`)
        }
      } else {
        toast.error('Failed to verify system status')
      }
    } catch (error) {
      console.error('Verification error:', error)
      toast.error('Failed to verify system - backend may not be running')
    } finally {
      setVerifying(false)
    }
  }

  const checkSetupStatus = async () => {
    try {
      setLoading(true)
      setBackendError(null)
      const response = await fetch(`${BACKEND_URL}/api/setup/status`)
      
      if (!response.ok) {
        if (response.status === 500) {
          setBackendError("Unable to connect to backend server. This is expected if the backend is not running yet. You can proceed with the setup wizard below to configure your secrets. Once configured, restart the backend server and click 'Retry' to verify.")
          return
        }
        if (response.status === 502 || response.status === 503) {
          setBackendError("Backend server is not running. This is normal for initial setup. Please proceed with configuring your secrets below. After adding secrets to Replit, restart the backend server and click 'Retry' to verify your configuration.")
          return
        }
        // Try to get error message from response
        let errorMessage = `Unable to verify setup status (HTTP ${response.status}). This is expected if the backend is not running. You can proceed with the setup wizard below to configure your secrets.`
        try {
          const errorData = await response.json()
          if (errorData.message || errorData.error) {
            errorMessage = `${errorData.message || errorData.error} - You can still proceed with configuration below.`
          }
        } catch {
          // Ignore JSON parse errors
        }
        setBackendError(errorMessage)
        return
      }
      
      const data = await response.json()
      setStatus(data)
      
      // If already configured, redirect to login
      if (data.ready) {
        localStorage.removeItem('setup_step')
        toast.success("Setup complete! Redirecting to login...")
        setTimeout(() => router.push('/login'), 2000)
      }
    } catch (error) {
      console.error("Failed to check setup status:", error)
      setBackendError("Unable to connect to backend server. This is expected if the backend is not running yet. You can proceed with the setup wizard below to configure your secrets. Once configured, restart the backend server and click 'Retry' to verify.")
      // Don't show toast error - this is expected during initial setup
    } finally {
      setLoading(false)
    }
  }

  const generateSecureString = (length: number = 32): string => {
    // Use crypto.getRandomValues for cryptographically secure random generation
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*'
    const array = new Uint8Array(length)
    
    if (typeof window !== 'undefined' && window.crypto && window.crypto.getRandomValues) {
      window.crypto.getRandomValues(array)
    } else {
      // Fallback for older browsers (less secure)
      for (let i = 0; i < length; i++) {
        array[i] = Math.floor(Math.random() * 256)
      }
    }
    
    return Array.from(array, byte => chars[byte % chars.length]).join('')
  }

  const generateAdminKey = () => {
    const key = generateSecureString(32)
    setAdminKey(key)
    copyToClipboard(key, 'admin-key')
  }

  const generateJwtSecret = () => {
    const secret = generateSecureString(64)
    setJwtSecret(secret)
    copyToClipboard(secret, 'jwt-secret')
  }

  const generateHmacSecret = () => {
    const secret = generateSecureString(64)
    setHmacSecret(secret)
    copyToClipboard(secret, 'hmac-secret')
  }
  
  const constructDatabaseUrl = () => {
    if (usePostgresParams && pgHost && pgUser && pgPassword && pgDatabase) {
      const port = pgPort || "5432"
      return `postgresql://${encodeURIComponent(pgUser)}:${encodeURIComponent(pgPassword)}@${pgHost}:${port}/${pgDatabase}`
    }
    return databaseUrl
  }

  const generateKeystorePassword = () => {
    const password = generateSecureString(24)
    setKeystorePassword(password)
    copyToClipboard(password, 'keystore-password')
  }

  const generateKeyPassword = () => {
    const password = generateSecureString(24)
    setKeyPassword(password)
    copyToClipboard(password, 'key-password')
  }

  const copyToClipboard = async (text: string, id: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(id)
      toast.success("Copied to clipboard!")
      setTimeout(() => setCopied(null), 2000)
    } catch (error) {
      toast.error("Failed to copy to clipboard")
    }
  }

  const validateFirebase = async () => {
    if (!firebaseJson.trim()) {
      setFirebaseValid(false)
      setFirebaseMessage("Please paste Firebase service account JSON")
      return
    }

    setFirebaseValidating(true)
    setFirebaseValid(null)
    setFirebaseMessage("")
    
    try {
      const response = await fetch(`${BACKEND_URL}/api/setup/validate-firebase`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ firebase_json: firebaseJson })
      })
      
      if (!response.ok) {
        // Handle non-OK responses
        // If backend is unavailable (500/502/503), treat as network error and allow proceeding
        if (response.status === 500 || response.status === 502 || response.status === 503) {
          setFirebaseValid(null) // Set to null to allow proceeding
          const errorMsg = `Backend server is not running (HTTP ${response.status}). This is expected during initial setup. You can proceed if your JSON looks correct.`
          setFirebaseMessage(errorMsg)
          toast.warning("Backend unavailable - you can proceed if JSON looks correct.")
          return
        }
        
        // For other HTTP errors (400, 401, etc.), treat as validation failure
        let errorMessage = `Validation failed (HTTP ${response.status})`
        try {
          const errorData = await response.json()
          errorMessage = errorData.message || errorData.error || errorMessage
        } catch {
          // If response isn't JSON, use status text
          errorMessage = response.statusText || errorMessage
        }
        setFirebaseValid(false)
        setFirebaseMessage(errorMessage)
        toast.error(errorMessage)
        return
      }
      
      const data = await response.json()
      setFirebaseValid(data.valid)
      setFirebaseMessage(data.message)
      
      if (data.valid) {
        toast.success("Firebase JSON is valid!")
      } else {
        toast.error(data.message)
      }
    } catch (error) {
      // Network error or backend unreachable
      setFirebaseValid(null) // Set to null instead of false to allow proceeding
      const errorMsg = error instanceof Error 
        ? `Unable to validate: ${error.message}. Backend may not be running. You can still proceed if your JSON looks correct.`
        : "Unable to validate Firebase JSON. Backend may not be running. You can still proceed if your JSON looks correct."
      setFirebaseMessage(errorMsg)
      toast.warning("Validation unavailable - backend may not be running. You can proceed if JSON looks correct.")
    } finally {
      setFirebaseValidating(false)
    }
  }

  const progress = ((currentStep + 1) / steps.length) * 100

  // Save progress to localStorage
  const handleStepChange = (newStep: number) => {
    setCurrentStep(newStep)
    localStorage.setItem('setup_step', newStep.toString())
  }

  if (loading && !backendError) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center">
          <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4" />
          <p className="text-muted-foreground">Checking setup status...</p>
        </div>
      </div>
    )
  }

  if (status?.ready && !backendError) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5 text-green-500" />
              Setup Complete
            </CardTitle>
            <CardDescription>All required configuration is set. Redirecting...</CardDescription>
          </CardHeader>
        </Card>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold mb-2">NexMDM Setup Wizard</h1>
          <p className="text-muted-foreground">Configure your MDM instance step by step</p>
        </div>

        {/* Backend Status Alert */}
        {backendError && (
          <Alert className="mb-6 border-yellow-500/50 bg-yellow-50 dark:bg-yellow-950/20">
            <Info className="h-4 w-4 text-yellow-600 dark:text-yellow-500" />
            <AlertDescription className="text-yellow-800 dark:text-yellow-300">
              {backendError}
              <Button
                variant="outline"
                size="sm"
                className="ml-4 border-yellow-600 text-yellow-700 hover:bg-yellow-100 dark:border-yellow-500 dark:text-yellow-400 dark:hover:bg-yellow-900/30"
                onClick={checkSetupStatus}
              >
                Retry
              </Button>
            </AlertDescription>
          </Alert>
        )}

        {/* Progress */}
        <div className="mb-8">
          <div className="flex justify-between mb-2 text-sm text-muted-foreground">
            <span>Step {currentStep + 1} of {steps.length}</span>
            <span>{Math.round(progress)}%</span>
          </div>
          <Progress value={progress} className="h-2" />
        </div>

        {/* Step Content */}
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              {(() => {
                const Icon = steps[currentStep].icon
                return Icon && <Icon className="h-5 w-5" />
              })()}
              {steps[currentStep].title}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {/* Step 0: Welcome */}
            {currentStep === 0 && (
              <div className="space-y-4">
                <p className="text-muted-foreground">
                  Welcome! This wizard will help you configure NexMDM for deployment on Replit.
                  We'll guide you through setting up all required secrets and optional integrations.
                </p>
                <Alert>
                  <AlertDescription>
                    <strong>Important:</strong> You'll need to add secrets in Replit's Secrets tab. Each secret requires two inputs: the secret name (e.g., <code>ADMIN_KEY</code>) and the secret value. This wizard will generate secure values and provide copy-paste instructions. To access Secrets, click the <strong>"+"</strong> button in Replit and select <strong>"Secrets"</strong>.
                  </AlertDescription>
                </Alert>
                <div className="space-y-2">
                  <h3 className="font-semibold">What we'll configure:</h3>
                  <ul className="list-disc list-inside space-y-1 text-sm text-muted-foreground">
                    <li>Admin API key, JWT secret (SESSION_SECRET), and HMAC secret</li>
                    <li>Firebase Cloud Messaging credentials</li>
                    <li>Database configuration (PostgreSQL recommended)</li>
                    <li>GitHub Actions secrets (optional, for Android CI/CD)</li>
                    <li>Discord webhook (optional, for alerts)</li>
                    <li>Android keystore setup (optional)</li>
                  </ul>
                </div>
                <Button onClick={() => handleStepChange(1)} className="w-full">
                  Get Started <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </div>
            )}

            {/* Step 1: Admin Credentials */}
            {currentStep === 1 && (
              <div className="space-y-6">
                <Alert>
                  <AlertDescription>
                    Generate secure credentials for admin API access and JWT authentication.
                  </AlertDescription>
                </Alert>

                {/* Admin Key */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <Label htmlFor="admin-key">ADMIN_KEY</Label>
                    <Badge variant={status?.required.admin_key.configured ? "default" : "destructive"}>
                      {status?.required.admin_key.configured ? "Configured" : "Required"}
                    </Badge>
                  </div>
                  <div className="flex gap-2">
                    <Input
                      id="admin-key"
                      value={adminKey}
                      onChange={(e) => setAdminKey(e.target.value)}
                      placeholder="Click Generate to create a secure key"
                      readOnly
                    />
                    <Button
                      type="button"
                      variant="outline"
                      onClick={generateAdminKey}
                      className="shrink-0"
                    >
                      Generate
                    </Button>
                    {adminKey && (
                      <Button
                        type="button"
                        variant="outline"
                        size="icon"
                        onClick={() => copyToClipboard(adminKey, 'admin-key')}
                      >
                        {copied === 'admin-key' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                      </Button>
                    )}
                  </div>
                  {adminKey && (
                    <div className="bg-muted p-4 rounded-md">
                      <p className="text-sm font-mono mb-2">Add to Replit Secrets:</p>
                      <div className="flex items-center gap-2">
                        <code className="text-xs flex-1 bg-background p-2 rounded break-all">
                          ADMIN_KEY={adminKey}
                        </code>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          onClick={() => copyToClipboard(`ADMIN_KEY=${adminKey}`, 'admin-key-full')}
                        >
                          {copied === 'admin-key-full' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                        </Button>
                      </div>
                    </div>
                  )}
                </div>

                {/* JWT Secret */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <Label htmlFor="jwt-secret">SESSION_SECRET</Label>
                    <Badge variant={status?.required.jwt_secret.configured ? "default" : "destructive"}>
                      {status?.required.jwt_secret.configured ? "Configured" : "Required"}
                    </Badge>
                  </div>
                  <div className="flex gap-2">
                    <Input
                      id="jwt-secret"
                      value={jwtSecret}
                      onChange={(e) => setJwtSecret(e.target.value)}
                      placeholder="Click Generate to create a secure secret"
                      readOnly
                    />
                    <Button
                      type="button"
                      variant="outline"
                      onClick={generateJwtSecret}
                      className="shrink-0"
                    >
                      Generate
                    </Button>
                    {jwtSecret && (
                      <Button
                        type="button"
                        variant="outline"
                        size="icon"
                        onClick={() => copyToClipboard(jwtSecret, 'jwt-secret')}
                      >
                        {copied === 'jwt-secret' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                      </Button>
                    )}
                  </div>
                  {jwtSecret && (
                    <div className="bg-muted p-4 rounded-md">
                      <p className="text-sm font-mono mb-2">Add to Replit Secrets:</p>
                      <div className="flex items-center gap-2">
                        <code className="text-xs flex-1 bg-background p-2 rounded break-all">
                          SESSION_SECRET={jwtSecret}
                        </code>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          onClick={() => copyToClipboard(`SESSION_SECRET=${jwtSecret}`, 'jwt-secret-full')}
                        >
                          {copied === 'jwt-secret-full' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                        </Button>
                      </div>
                    </div>
                  )}
                  
                  {/* Warning about pre-populated SESSION_SECRET */}
                  <Alert className="border-yellow-500/50 bg-yellow-50 dark:bg-yellow-950/20">
                    <AlertCircle className="h-4 w-4 text-yellow-600 dark:text-yellow-500" />
                    <AlertDescription className="text-yellow-800 dark:text-yellow-300 text-sm">
                      <strong>Important:</strong> If <code>SESSION_SECRET</code> already exists in Replit Secrets, it may be an insecure default value. Please replace it with the secure value generated above. The setup wizard will verify that you're using a secure value.
                    </AlertDescription>
                  </Alert>
                  
                  {/* Note about JWT_SECRET */}
                  <Alert className="border-blue-500/50 bg-blue-50 dark:bg-blue-950/20">
                    <Info className="h-4 w-4 text-blue-600 dark:text-blue-400" />
                    <AlertDescription className="text-blue-800 dark:text-blue-300 text-sm">
                      <strong>Note:</strong> <code>JWT_SECRET</code> is the same as <code>SESSION_SECRET</code>. The application uses <code>SESSION_SECRET</code> for JWT token signing.
                    </AlertDescription>
                  </Alert>
                </div>

                {/* HMAC Secret */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <Label htmlFor="hmac-secret">HMAC_SECRET</Label>
                    <Badge variant={status?.required.hmac_secret?.configured && status?.required.hmac_secret?.valid ? "default" : "destructive"}>
                      {status?.required.hmac_secret?.configured && status?.required.hmac_secret?.valid ? "Configured" : "Required"}
                    </Badge>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    Required for device command authentication. Used to sign FCM commands sent to Android devices.
                  </p>
                  <div className="flex gap-2">
                    <Input
                      id="hmac-secret"
                      value={hmacSecret}
                      onChange={(e) => setHmacSecret(e.target.value)}
                      placeholder="Click Generate to create a secure secret"
                      readOnly
                    />
                    <Button
                      type="button"
                      variant="outline"
                      onClick={generateHmacSecret}
                      className="shrink-0"
                    >
                      Generate
                    </Button>
                    {hmacSecret && (
                      <Button
                        type="button"
                        variant="outline"
                        size="icon"
                        onClick={() => copyToClipboard(hmacSecret, 'hmac-secret')}
                      >
                        {copied === 'hmac-secret' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                      </Button>
                    )}
                  </div>
                  {hmacSecret && (
                    <div className="bg-muted p-4 rounded-md">
                      <p className="text-sm font-mono mb-2">Add to Replit Secrets:</p>
                      <div className="flex items-center gap-2">
                        <code className="text-xs flex-1 bg-background p-2 rounded break-all">
                          HMAC_SECRET={hmacSecret}
                        </code>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          onClick={() => copyToClipboard(`HMAC_SECRET=${hmacSecret}`, 'hmac-secret-full')}
                        >
                          {copied === 'hmac-secret-full' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                        </Button>
                      </div>
                    </div>
                  )}
                </div>

                <Alert>
                  <AlertDescription>
                    <strong>Next steps:</strong>
                    <ol className="list-decimal list-inside mt-2 space-y-1 text-sm">
                      <li>Copy the generated values above (you'll need both the secret name and value)</li>
                      <li>In Replit, click the <strong>"+"</strong> button to open a new tab</li>
                      <li>Select <strong>"Secrets"</strong> from the tab options (or look for the 🔒 icon)</li>
                      <li>For each secret, you need to add two things:
                        <ul className="list-disc list-inside ml-4 mt-1 space-y-1">
                          <li><strong>Secret Name:</strong> Enter the exact name shown (e.g., <code>ADMIN_KEY</code>, <code>SESSION_SECRET</code>, or <code>HMAC_SECRET</code>)</li>
                          <li><strong>Secret Value:</strong> Paste the generated value from above</li>
                        </ul>
                      </li>
                      <li>Click <strong>"Add Secret"</strong> for each secret</li>
                      <li>Return here and click <strong>"Check Configuration"</strong> to verify</li>
                    </ol>
                  </AlertDescription>
                </Alert>

                <div className="flex gap-2">
                  <Button variant="outline" onClick={() => handleStepChange(0)}>
                    <ArrowLeft className="mr-2 h-4 w-4" /> Back
                  </Button>
                  <Button
                    onClick={async () => {
                      setChecking(true)
                      await checkSetupStatus()
                      setChecking(false)
                      if (adminKey && jwtSecret && hmacSecret) {
                        handleStepChange(2)
                      } else {
                        toast.info("Please generate and add all secrets to Replit first")
                      }
                    }}
                    disabled={checking}
                    className="flex-1"
                  >
                    {checking ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Checking...
                      </>
                    ) : (
                      <>
                        Check Configuration <ArrowRight className="ml-2 h-4 w-4" />
                      </>
                    )}
                  </Button>
                </div>
              </div>
            )}

            {/* Step 2: Firebase */}
            {currentStep === 2 && (
              <div className="space-y-6">
                <Alert>
                  <AlertDescription>
                    Firebase Cloud Messaging (FCM) is required for push notifications to Android devices.
                  </AlertDescription>
                </Alert>

                <div className="space-y-4">
                  <div>
                    <h3 className="font-semibold mb-2">How to get Firebase credentials:</h3>
                    <ol className="list-decimal list-inside space-y-2 text-sm text-muted-foreground mb-4">
                      <li>Go to <a href="https://console.firebase.google.com" target="_blank" rel="noopener noreferrer" className="text-primary underline inline-flex items-center gap-1">Firebase Console <ExternalLink className="h-3 w-3" /></a></li>
                      <li>Create a new project or select an existing one</li>
                      <li>
                        <strong>Enable Firebase Cloud Messaging (FCM):</strong>
                        <ul className="list-disc list-inside ml-4 mt-1 space-y-1">
                          <li>Go to <strong>Project Settings</strong> → <strong>Cloud Messaging</strong> tab</li>
                          <li>Ensure Firebase Cloud Messaging API is enabled (it should be enabled by default)</li>
                        </ul>
                      </li>
                      <li>
                        <strong>Add an Android app to your Firebase project (if not already added):</strong>
                        <ul className="list-disc list-inside ml-4 mt-1 space-y-1">
                          <li>Click the Android icon or "Add app" → Select Android</li>
                          <li>Enter your Android package name (e.g., <code className="bg-background px-1 py-0.5 rounded">com.nexmdm.app</code>)</li>
                          <li>Follow the setup wizard to complete Android app registration</li>
                        </ul>
                      </li>
                      <li>
                        <strong>Get Service Account JSON:</strong>
                        <ul className="list-disc list-inside ml-4 mt-1 space-y-1">
                          <li>Navigate to <strong>Project Settings</strong> (gear icon) → <strong>General</strong> tab</li>
                          <li>Scroll down to the <strong>"Your apps"</strong> section</li>
                          <li>Click on <strong>"Service accounts"</strong> tab</li>
                          <li>Click <strong>"Generate new private key"</strong></li>
                          <li>Click <strong>"Generate key"</strong> in the confirmation dialog</li>
                          <li>The JSON file will download automatically</li>
                        </ul>
                      </li>
                      <li>Open the downloaded JSON file and paste the entire content below</li>
                    </ol>
                    <Alert className="border-yellow-500/50 bg-yellow-50 dark:bg-yellow-950/20">
                      <Info className="h-4 w-4 text-yellow-600 dark:text-yellow-400" />
                      <AlertDescription className="text-yellow-800 dark:text-yellow-300 text-sm">
                        <strong>Tip:</strong> The Service Accounts tab is located in Project Settings → General tab, not in the Cloud Messaging section. 
                        Scroll down past the "Your apps" section to find it.
                      </AlertDescription>
                    </Alert>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="firebase-json">Firebase Service Account JSON</Label>
                    <Textarea
                      id="firebase-json"
                      value={firebaseJson}
                      onChange={(e) => {
                        setFirebaseJson(e.target.value)
                        setFirebaseValid(null)
                        setFirebaseMessage("")
                      }}
                      placeholder='{"type": "service_account", "project_id": "...", ...}'
                      rows={8}
                      className="font-mono text-xs"
                    />
                    <div className="flex gap-2 items-center">
                      <Button
                        type="button"
                        variant="outline"
                        onClick={validateFirebase}
                        disabled={firebaseValidating || !firebaseJson.trim()}
                      >
                        {firebaseValidating ? (
                          <>
                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            Validating...
                          </>
                        ) : (
                          "Validate JSON"
                        )}
                      </Button>
                      {firebaseValid === true && (
                        <Badge variant="default" className="flex items-center gap-1">
                          <CheckCircle2 className="h-3 w-3" />
                          Valid
                        </Badge>
                      )}
                      {firebaseValid === false && (
                        <Badge variant="destructive" className="flex items-center gap-1">
                          <XCircle className="h-3 w-3" />
                          Invalid
                        </Badge>
                      )}
                      {firebaseValid === null && firebaseMessage && (
                        <Badge variant="outline" className="flex items-center gap-1 border-yellow-500 text-yellow-700 dark:text-yellow-400">
                          <AlertCircle className="h-3 w-3" />
                          Backend Unavailable
                        </Badge>
                      )}
                    </div>
                    {firebaseMessage && (
                      <p className={`text-sm ${
                        firebaseValid === true 
                          ? 'text-green-600 dark:text-green-400' 
                          : firebaseValid === false
                          ? 'text-red-600 dark:text-red-400'
                          : 'text-yellow-600 dark:text-yellow-400'
                      }`}>
                        {firebaseMessage}
                      </p>
                    )}
                  </div>

                  {(firebaseValid === true || (firebaseValid === null && firebaseJson.trim())) && (
                    <div className="bg-muted p-4 rounded-md space-y-4">
                      <div>
                        <p className="text-sm font-semibold mb-2">Add to Replit Secrets:</p>
                        <ol className="list-decimal list-inside space-y-2 text-sm mb-4">
                          <li>Click the <strong>"+"</strong> button in the Replit Secrets tab</li>
                          <li>In the <strong>"Secret Name"</strong> field, enter: <code className="bg-background px-1 py-0.5 rounded">FIREBASE_SERVICE_ACCOUNT_JSON</code></li>
                          <li>In the <strong>"Secret Value"</strong> field, paste the JSON below (as a single-line string)</li>
                          <li>Click <strong>"Add Secret"</strong></li>
                        </ol>
                      </div>
                      <div className="space-y-2">
                        <div>
                          <Label className="text-xs font-semibold">Secret Name:</Label>
                          <div className="flex items-center gap-2 mt-1">
                            <code className="text-xs flex-1 bg-background p-2 rounded">
                              FIREBASE_SERVICE_ACCOUNT_JSON
                            </code>
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              onClick={() => copyToClipboard('FIREBASE_SERVICE_ACCOUNT_JSON', 'firebase-secret-name')}
                            >
                              {copied === 'firebase-secret-name' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                            </Button>
                          </div>
                        </div>
                        <div>
                          <Label className="text-xs font-semibold">Secret Value (paste this JSON):</Label>
                          <div className="flex items-center gap-2 mt-1">
                            <code className="text-xs flex-1 bg-background p-2 rounded break-all font-mono">
                              {(() => {
                                try {
                                  return JSON.stringify(JSON.parse(firebaseJson))
                                } catch {
                                  return firebaseJson.trim()
                                }
                              })()}
                            </code>
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              onClick={() => {
                                try {
                                  const jsonStr = JSON.stringify(JSON.parse(firebaseJson))
                                  copyToClipboard(jsonStr, 'firebase-json-value')
                                } catch (e) {
                                  copyToClipboard(firebaseJson.trim(), 'firebase-json-value')
                                }
                              }}
                            >
                              {copied === 'firebase-json-value' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                            </Button>
                          </div>
                        </div>
                        <p className="text-xs text-muted-foreground">
                          Note: Paste the JSON as a single-line string (no line breaks) in the Secret Value field.
                        </p>
                      </div>
                    </div>
                  )}
                </div>

                <div className="flex gap-2">
                  <Button variant="outline" onClick={() => handleStepChange(1)}>
                    <ArrowLeft className="mr-2 h-4 w-4" /> Back
                  </Button>
                  <Button
                    onClick={async () => {
                      // Only require validation if it was attempted and explicitly failed (not due to backend unavailability)
                      // Allow proceeding if:
                      // - Validation hasn't been attempted (firebaseValid === null)
                      // - Backend is unavailable (firebaseValid === null with backend error message)
                      // - Validation passed (firebaseValid === true)
                      if (firebaseValid === false && firebaseMessage && !firebaseMessage.includes("Backend") && !firebaseMessage.includes("backend")) {
                        toast.error("Please fix Firebase JSON errors before continuing")
                        return
                      }
                      // Require at least some JSON content
                      if (!firebaseJson.trim()) {
                        toast.error("Please paste Firebase service account JSON")
                        return
                      }
                      setChecking(true)
                      await checkSetupStatus()
                      setChecking(false)
                      handleStepChange(3) // Go to database step
                    }}
                    disabled={checking || (firebaseValid === false && firebaseMessage && !firebaseMessage.includes("Backend") && !firebaseMessage.includes("backend")) || !firebaseJson.trim()}
                    className="flex-1"
                  >
                    {checking ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Checking...
                      </>
                    ) : (
                      <>
                        Continue <ArrowRight className="ml-2 h-4 w-4" />
                      </>
                    )}
                  </Button>
                </div>
              </div>
            )}

            {/* Step 3: Database Configuration */}
            {currentStep === 3 && (
              <div className="space-y-6">
                <Alert>
                  <AlertDescription>
                    Configure your database connection. PostgreSQL is recommended for production, but SQLite works for development.
                  </AlertDescription>
                </Alert>

                {/* Current Database Status */}
                {status && status.required.database && (
                  <div className="space-y-3">
                    {status.required.database.configured && status.required.database.valid && (
                      <Alert className="border-green-500/50 bg-green-50 dark:bg-green-950/20">
                        <CheckCircle2 className="h-5 w-5 text-green-600 dark:text-green-400" />
                        <AlertDescription className="text-green-800 dark:text-green-300">
                          <div className="flex items-center justify-between">
                            <div>
                              <strong>Database configured and connected!</strong>
                              <p className="text-sm mt-1">
                                {status.required.database.type && (
                                  <span className="capitalize">{status.required.database.type}</span>
                                )} {status.required.database.message}
                              </p>
                            </div>
                            <Badge variant="outline" className="bg-green-100 dark:bg-green-900">
                              Connected
                            </Badge>
                          </div>
                        </AlertDescription>
                      </Alert>
                    )}
                    {status.required.database.configured && !status.required.database.valid && (
                      <Alert className="border-red-500/50 bg-red-50 dark:bg-red-950/20">
                        <XCircle className="h-5 w-5 text-red-600 dark:text-red-400" />
                        <AlertDescription className="text-red-800 dark:text-red-300">
                          <strong>Database configured but connection failed</strong>
                          <p className="text-sm mt-1">{status.required.database.message}</p>
                        </AlertDescription>
                      </Alert>
                    )}
                    {!status.required.database.configured && (
                      <Alert className="border-yellow-500/50 bg-yellow-50 dark:bg-yellow-950/20">
                        <AlertCircle className="h-5 w-5 text-yellow-600 dark:text-yellow-500" />
                        <AlertDescription className="text-yellow-800 dark:text-yellow-300">
                          <strong>Using default SQLite database</strong>
                          <p className="text-sm mt-1">PostgreSQL is recommended for production deployments.</p>
                        </AlertDescription>
                      </Alert>
                    )}
                  </div>
                )}

                {/* Database Test Result */}
                {databaseTestResult && (
                  <Alert className={databaseTestResult.connected 
                    ? "border-green-500/50 bg-green-50 dark:bg-green-950/20"
                    : "border-red-500/50 bg-red-50 dark:bg-red-950/20"
                  }>
                    {databaseTestResult.connected ? (
                      <CheckCircle2 className="h-5 w-5 text-green-600 dark:text-green-400" />
                    ) : (
                      <XCircle className="h-5 w-5 text-red-600 dark:text-red-400" />
                    )}
                    <AlertDescription className={databaseTestResult.connected
                      ? "text-green-800 dark:text-green-300"
                      : "text-red-800 dark:text-red-300"
                    }>
                      <strong>{databaseTestResult.connected ? 'Connection successful!' : 'Connection failed'}</strong>
                      <p className="text-sm mt-1">{databaseTestResult.message}</p>
                      {databaseTestResult.type && (
                        <p className="text-xs mt-1">Database type: {databaseTestResult.type}</p>
                      )}
                    </AlertDescription>
                  </Alert>
                )}

                <div className="space-y-4">
                  <div>
                    <h3 className="font-semibold mb-2">Database Configuration Options:</h3>
                    
                    {/* Option A: Replit PostgreSQL */}
                    <Card className="mb-4">
                      <CardHeader className="pb-3">
                        <CardTitle className="text-base flex items-center gap-2">
                          <Database className="h-4 w-4" />
                          Option A: Use Replit PostgreSQL (Recommended)
                        </CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-3">
                        <p className="text-sm text-muted-foreground">
                          Replit PostgreSQL integration automatically sets up <code>DATABASE_URL</code> for you.
                        </p>
                        <ol className="list-decimal list-inside space-y-2 text-sm text-muted-foreground">
                          <li>In Replit, click the <strong>"+"</strong> button to open a new tab</li>
                          <li>Search for and select <strong>"PostgreSQL"</strong> from the integrations</li>
                          <li>Click <strong>"Add Integration"</strong></li>
                          <li>Replit will automatically set <code>DATABASE_URL</code> in your Secrets</li>
                          <li>Return here and click <strong>"Test Connection"</strong> to verify</li>
                        </ol>
                        <Alert className="border-blue-500/50 bg-blue-50 dark:bg-blue-950/20">
                          <Info className="h-4 w-4 text-blue-600 dark:text-blue-400" />
                          <AlertDescription className="text-blue-800 dark:text-blue-300 text-sm">
                            After adding PostgreSQL integration, you may need to restart the backend for the connection to be recognized.
                          </AlertDescription>
                        </Alert>
                      </CardContent>
                    </Card>

                    {/* Option B: Manual DATABASE_URL */}
                    <Card className="mb-4">
                      <CardHeader className="pb-3">
                        <CardTitle className="text-base flex items-center gap-2">
                          <Database className="h-4 w-4" />
                          Option B: Manual DATABASE_URL Entry
                        </CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-3">
                        <div className="space-y-2">
                          <Label htmlFor="database-url">DATABASE_URL</Label>
                          <Input
                            id="database-url"
                            value={databaseUrl}
                            onChange={(e) => {
                              setDatabaseUrl(e.target.value)
                              const url = e.target.value.toLowerCase()
                              if (url.includes('postgres')) {
                                setDatabaseType('postgresql')
                              } else if (url.includes('sqlite')) {
                                setDatabaseType('sqlite')
                              } else {
                                setDatabaseType('manual')
                              }
                            }}
                            placeholder="postgresql://user:password@host:port/database or sqlite:///./data.db"
                            className="font-mono text-sm"
                          />
                          <p className="text-xs text-muted-foreground">
                            Format: <code>postgresql://user:password@host:port/database</code> or <code>sqlite:///./data.db</code>
                          </p>
                        </div>
                        {databaseUrl && (
                          <div className="bg-muted p-4 rounded-md">
                            <p className="text-sm font-mono mb-2">Add to Replit Secrets:</p>
                            <div className="flex items-center gap-2">
                              <code className="text-xs flex-1 bg-background p-2 rounded break-all">
                                DATABASE_URL={databaseUrl}
                              </code>
                              <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                onClick={() => copyToClipboard(`DATABASE_URL=${databaseUrl}`, 'database-url-full')}
                              >
                                {copied === 'database-url-full' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                              </Button>
                            </div>
                          </div>
                        )}
                      </CardContent>
                    </Card>

                    {/* Option C: PostgreSQL Individual Parameters */}
                    <Card>
                      <CardHeader className="pb-3">
                        <CardTitle className="text-base flex items-center gap-2">
                          <Database className="h-4 w-4" />
                          Option C: PostgreSQL Individual Parameters
                        </CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-3">
                        <div className="flex items-center space-x-2">
                          <Checkbox
                            id="use-postgres-params"
                            checked={usePostgresParams}
                            onCheckedChange={(checked) => setUsePostgresParams(checked === true)}
                          />
                          <Label htmlFor="use-postgres-params" className="text-sm">
                            Use individual PostgreSQL parameters instead of DATABASE_URL
                          </Label>
                        </div>
                        {usePostgresParams && (
                          <div className="space-y-3 pl-6 border-l-2">
                            <div className="grid grid-cols-2 gap-3">
                              <div className="space-y-2">
                                <Label htmlFor="pg-host">PGHOST</Label>
                                <Input
                                  id="pg-host"
                                  value={pgHost}
                                  onChange={(e) => setPgHost(e.target.value)}
                                  placeholder="localhost"
                                />
                              </div>
                              <div className="space-y-2">
                                <Label htmlFor="pg-port">PGPORT</Label>
                                <Input
                                  id="pg-port"
                                  value={pgPort}
                                  onChange={(e) => setPgPort(e.target.value)}
                                  placeholder="5432"
                                />
                              </div>
                              <div className="space-y-2">
                                <Label htmlFor="pg-user">PGUSER</Label>
                                <Input
                                  id="pg-user"
                                  value={pgUser}
                                  onChange={(e) => setPgUser(e.target.value)}
                                  placeholder="postgres"
                                />
                              </div>
                              <div className="space-y-2">
                                <Label htmlFor="pg-password">PGPASSWORD</Label>
                                <Input
                                  id="pg-password"
                                  type="password"
                                  value={pgPassword}
                                  onChange={(e) => setPgPassword(e.target.value)}
                                  placeholder="password"
                                />
                              </div>
                              <div className="space-y-2 col-span-2">
                                <Label htmlFor="pg-database">PGDATABASE</Label>
                                <Input
                                  id="pg-database"
                                  value={pgDatabase}
                                  onChange={(e) => setPgDatabase(e.target.value)}
                                  placeholder="nexmdm"
                                />
                              </div>
                            </div>
                            {pgHost && pgUser && pgPassword && pgDatabase && (
                              <div className="bg-muted p-4 rounded-md">
                                <p className="text-sm font-semibold mb-2">Add these to Replit Secrets:</p>
                                <div className="space-y-2 text-xs font-mono">
                                  <div className="flex items-center gap-2">
                                    <code className="flex-1 bg-background p-2 rounded">
                                      PGHOST={pgHost}
                                    </code>
                                    <Button
                                      type="button"
                                      variant="ghost"
                                      size="icon"
                                      onClick={() => copyToClipboard(`PGHOST=${pgHost}`, 'pg-host')}
                                    >
                                      {copied === 'pg-host' ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                                    </Button>
                                  </div>
                                  <div className="flex items-center gap-2">
                                    <code className="flex-1 bg-background p-2 rounded">
                                      PGPORT={pgPort}
                                    </code>
                                    <Button
                                      type="button"
                                      variant="ghost"
                                      size="icon"
                                      onClick={() => copyToClipboard(`PGPORT=${pgPort}`, 'pg-port')}
                                    >
                                      {copied === 'pg-port' ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                                    </Button>
                                  </div>
                                  <div className="flex items-center gap-2">
                                    <code className="flex-1 bg-background p-2 rounded">
                                      PGUSER={pgUser}
                                    </code>
                                    <Button
                                      type="button"
                                      variant="ghost"
                                      size="icon"
                                      onClick={() => copyToClipboard(`PGUSER=${pgUser}`, 'pg-user')}
                                    >
                                      {copied === 'pg-user' ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                                    </Button>
                                  </div>
                                  <div className="flex items-center gap-2">
                                    <code className="flex-1 bg-background p-2 rounded">
                                      PGPASSWORD={pgPassword}
                                    </code>
                                    <Button
                                      type="button"
                                      variant="ghost"
                                      size="icon"
                                      onClick={() => copyToClipboard(`PGPASSWORD=${pgPassword}`, 'pg-password')}
                                    >
                                      {copied === 'pg-password' ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                                    </Button>
                                  </div>
                                  <div className="flex items-center gap-2">
                                    <code className="flex-1 bg-background p-2 rounded">
                                      PGDATABASE={pgDatabase}
                                    </code>
                                    <Button
                                      type="button"
                                      variant="ghost"
                                      size="icon"
                                      onClick={() => copyToClipboard(`PGDATABASE=${pgDatabase}`, 'pg-database')}
                                    >
                                      {copied === 'pg-database' ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                                    </Button>
                                  </div>
                                </div>
                                <Alert className="mt-3 border-yellow-500/50 bg-yellow-50 dark:bg-yellow-950/20">
                                  <AlertCircle className="h-4 w-4 text-yellow-600 dark:text-yellow-500" />
                                  <AlertDescription className="text-yellow-800 dark:text-yellow-300 text-xs">
                                    <strong>Note:</strong> The application uses <code>DATABASE_URL</code> by default. If you use individual PostgreSQL parameters, you may need to construct <code>DATABASE_URL</code> from these values: <code>postgresql://{pgUser}:{pgPassword}@{pgHost}:{pgPort}/{pgDatabase}</code>
                                  </AlertDescription>
                                </Alert>
                              </div>
                            )}
                          </div>
                        )}
                      </CardContent>
                    </Card>
                  </div>
                </div>

                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    onClick={() => handleStepChange(2)} // Back to Firebase
                  >
                    <ArrowLeft className="mr-2 h-4 w-4" /> Back
                  </Button>
                  <Button
                    onClick={testDatabaseConnection}
                    variant="outline"
                    disabled={testingDatabase}
                    className="flex-1"
                  >
                    {testingDatabase ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Testing Connection...
                      </>
                    ) : (
                      <>
                        <Database className="mr-2 h-4 w-4" />
                        Test Database Connection
                      </>
                    )}
                  </Button>
                  <Button
                    onClick={async () => {
                      setChecking(true)
                      await checkSetupStatus()
                      setChecking(false)
                      handleStepChange(4) // Go to GitHub CI step
                    }}
                    disabled={checking}
                    className="flex-1"
                  >
                    {checking ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Checking...
                      </>
                    ) : (
                      <>
                        Continue <ArrowRight className="ml-2 h-4 w-4" />
                      </>
                    )}
                  </Button>
                </div>
              </div>
            )}

            {/* Step 4: GitHub CI (Recommended) */}
            {currentStep === 4 && (
              <div className="space-y-6">
                <Alert className="border-blue-500/50 bg-blue-50 dark:bg-blue-950/20">
                  <Info className="h-4 w-4 text-blue-600 dark:text-blue-400" />
                  <AlertDescription className="text-blue-800 dark:text-blue-300">
                    <strong>Recommended:</strong> GitHub Actions CI/CD automates Android APK builds, making deployment much easier. 
                    If you're not familiar with Android Studio, we strongly recommend setting this up now.
                  </AlertDescription>
                </Alert>

                <div className="space-y-4">
                  <div className="flex items-center space-x-2 p-4 bg-muted rounded-md">
                    <Checkbox
                      id="skip-github"
                      checked={skipGitHubCI}
                      onCheckedChange={(checked) => setSkipGitHubCI(checked === true)}
                    />
                    <Label htmlFor="skip-github" className="text-sm font-normal cursor-pointer">
                      I'm familiar with Android Studio and will build APKs manually
                    </Label>
                  </div>

                  {!skipGitHubCI && (
                    <>
                      <Alert className="border-blue-500/50 bg-blue-50 dark:bg-blue-950/20">
                        <Info className="h-4 w-4 text-blue-600 dark:text-blue-400" />
                        <AlertDescription className="text-blue-800 dark:text-blue-300 text-sm">
                          <strong>Before you begin:</strong> You need an Android project ready before setting up GitHub CI/CD. 
                          If you already have an Android project, you can clone it to your repository. 
                          If you don't have one yet, you can skip GitHub CI/CD for now and set it up later once your Android project is ready.
                        </AlertDescription>
                      </Alert>

                      <div>
                        <h3 className="font-semibold mb-2">Step 1: Create GitHub Account</h3>
                        <p className="text-sm text-muted-foreground mb-4">
                          If you don't have a GitHub account yet, go to <a href="https://github.com" target="_blank" rel="noopener noreferrer" className="text-primary underline inline-flex items-center gap-1">github.com <ExternalLink className="h-3 w-3" /></a> and create one. 
                          Once you have an account, continue with the steps below.
                        </p>
                      </div>

                      <div>
                        <h3 className="font-semibold mb-2">Step 2: Install and Authenticate GitHub CLI</h3>
                        <p className="text-sm text-muted-foreground mb-2">
                          Run these commands in the Replit Shell:
                        </p>
                        <div className="bg-muted p-4 rounded-md space-y-3">
                          <div>
                            <Label className="text-xs font-semibold mb-1 block">1. Check if GitHub CLI is installed:</Label>
                            <div className="flex items-center gap-2">
                              <code className="text-xs flex-1 bg-background p-2 rounded">
                                gh --version
                              </code>
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                onClick={() => copyToClipboard('gh --version', 'gh-version')}
                              >
                                {copied === 'gh-version' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                              </Button>
                            </div>
                            <p className="text-xs text-muted-foreground mt-1">
                              If not installed, run: <code className="bg-background px-1 py-0.5 rounded">pkg install gh</code>
                            </p>
                          </div>
                          <div>
                            <Label className="text-xs font-semibold mb-1 block">2. Authenticate with GitHub:</Label>
                            <div className="flex items-center gap-2">
                              <code className="text-xs flex-1 bg-background p-2 rounded">
                                gh auth login
                              </code>
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                onClick={() => copyToClipboard('gh auth login', 'gh-auth')}
                              >
                                {copied === 'gh-auth' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                              </Button>
                            </div>
                            <p className="text-xs text-muted-foreground mt-1">
                              Follow the prompts to authenticate. Choose "HTTPS" and "Login with a web browser".
                            </p>
                          </div>
                        </div>
                      </div>

                      <div>
                        <h3 className="font-semibold mb-2">Step 3: Create GitHub Repository</h3>
                        <p className="text-sm text-muted-foreground mb-2">
                          Create a new repository for your Android project:
                        </p>
                        <div className="bg-muted p-4 rounded-md space-y-3">
                          <div>
                            <Label className="text-xs font-semibold mb-1 block">Create a new repository (replace &lt;repo-name&gt; with your desired name):</Label>
                            <div className="flex items-center gap-2">
                              <code className="text-xs flex-1 bg-background p-2 rounded">
                                gh repo create &lt;repo-name&gt; --public
                              </code>
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                onClick={() => copyToClipboard('gh repo create <repo-name> --public', 'gh-repo-create')}
                              >
                                {copied === 'gh-repo-create' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                              </Button>
                            </div>
                            <p className="text-xs text-muted-foreground mt-1">
                              Use <code className="bg-background px-1 py-0.5 rounded">--private</code> for a private repository instead.
                            </p>
                          </div>
                        </div>
                        <div className="mt-4 space-y-2">
                          <Label htmlFor="github-repo">Enter your repository name (owner/repo-name)</Label>
                          <div className="flex items-center gap-2">
                            <Input
                              id="github-repo"
                              value={githubRepo}
                              onChange={(e) => setGithubRepo(e.target.value)}
                              placeholder="e.g., davidsalasmdm/unitymdm-david"
                              className="font-mono text-sm"
                            />
                            {githubRepo && githubRepo.includes('/') && !githubRepo.includes(' ') && (
                              <CheckCircle2 className="h-5 w-5 text-green-500" />
                            )}
                          </div>
                          <p className="text-xs text-muted-foreground">
                            Copy this from the output of <code className="bg-background px-1 py-0.5 rounded">gh repo create</code> command above. 
                            Format: <code className="bg-background px-1 py-0.5 rounded">owner/repo-name</code>
                          </p>
                          {githubRepo && (!githubRepo.includes('/') || githubRepo.includes(' ')) && (
                            <Alert className="border-yellow-500/50 bg-yellow-50 dark:bg-yellow-950/20">
                              <AlertCircle className="h-4 w-4 text-yellow-600 dark:text-yellow-500" />
                              <AlertDescription className="text-yellow-800 dark:text-yellow-300 text-xs">
                                Repository name should be in the format <code className="bg-background px-1 py-0.5 rounded">owner/repo-name</code> (e.g., davidsalasmdm/unitymdm-david)
                              </AlertDescription>
                            </Alert>
                          )}
                        </div>
                      </div>

                      <div>
                        <h3 className="font-semibold mb-2">Step 4: Generate Android Keystore</h3>
                        <p className="text-sm text-muted-foreground mb-2">
                          Generate a keystore file for signing your Android APK:
                        </p>
                        <div className="bg-muted p-4 rounded-md">
                          <code className="text-xs block mb-2"># Run this in Replit Shell:</code>
                          <code className="text-xs block whitespace-pre-wrap break-all">
{`keytool -genkey -v \\
  -keystore release.keystore \\
  -alias nexmdm \\
  -keyalg RSA \\
  -keysize 2048 \\
  -validity 10000 \\
  -storepass YOUR_STORE_PASSWORD \\
  -keypass YOUR_KEY_PASSWORD`}
                          </code>
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="mt-2"
                            onClick={() => copyToClipboard(`keytool -genkey -v -keystore release.keystore -alias nexmdm -keyalg RSA -keysize 2048 -validity 10000 -storepass YOUR_STORE_PASSWORD -keypass YOUR_KEY_PASSWORD`, 'keystore-cmd')}
                          >
                            {copied === 'keystore-cmd' ? <Check className="h-4 w-4 mr-2" /> : <Copy className="h-4 w-4 mr-2" />}
                            Copy Command
                          </Button>
                          <p className="text-xs text-muted-foreground mt-2">
                            Replace <code className="bg-background px-1 py-0.5 rounded">YOUR_STORE_PASSWORD</code> and <code className="bg-background px-1 py-0.5 rounded">YOUR_KEY_PASSWORD</code> with secure passwords.
                          </p>
                        </div>
                      </div>

                      <div>
                        <h3 className="font-semibold mb-2">Step 5: Add Secrets to GitHub Repository</h3>
                        <p className="text-sm text-muted-foreground mb-2">
                          Add the required secrets to your GitHub repository using the CLI:
                        </p>
                        <div className="bg-muted p-4 rounded-md space-y-3">
                          <div>
                            <Label className="text-xs font-semibold mb-1 block">1. Add keystore (Base64-encoded):</Label>
                            <div className="flex items-center gap-2">
                              <code className="text-xs flex-1 bg-background p-2 rounded break-all">
                                {`gh secret set ANDROID_KEYSTORE_BASE64 --repo ${githubRepo || '<owner>/<repo-name>'} --body "$(base64 -w 0 release.keystore)"`}
                              </code>
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                onClick={() => copyToClipboard(`gh secret set ANDROID_KEYSTORE_BASE64 --repo ${githubRepo || '<owner>/<repo-name>'} --body "$(base64 -w 0 release.keystore)"`, 'gh-secret-keystore')}
                              >
                                {copied === 'gh-secret-keystore' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                              </Button>
                            </div>
                            {!githubRepo && (
                              <p className="text-xs text-yellow-600 dark:text-yellow-400 mt-1">
                                ⚠️ Enter your repository name above to use the correct repository
                              </p>
                            )}
                          </div>
                          <div>
                            <Label className="text-xs font-semibold mb-1 block">2. Add keystore password:</Label>
                            <div className="flex items-center gap-2">
                              <code className="text-xs flex-1 bg-background p-2 rounded break-all">
                                {`gh secret set KEYSTORE_PASSWORD --repo ${githubRepo || '<owner>/<repo-name>'} --body "YOUR_STORE_PASSWORD"`}
                              </code>
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                onClick={() => copyToClipboard(`gh secret set KEYSTORE_PASSWORD --repo ${githubRepo || '<owner>/<repo-name>'} --body "YOUR_STORE_PASSWORD"`, 'gh-secret-storepass')}
                              >
                                {copied === 'gh-secret-storepass' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                              </Button>
                            </div>
                          </div>
                          <div>
                            <Label className="text-xs font-semibold mb-1 block">3. Add key alias:</Label>
                            <div className="flex items-center gap-2">
                              <code className="text-xs flex-1 bg-background p-2 rounded break-all">
                                {`gh secret set ANDROID_KEY_ALIAS --repo ${githubRepo || '<owner>/<repo-name>'} --body "nexmdm"`}
                              </code>
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                onClick={() => copyToClipboard(`gh secret set ANDROID_KEY_ALIAS --repo ${githubRepo || '<owner>/<repo-name>'} --body "nexmdm"`, 'gh-secret-alias')}
                              >
                                {copied === 'gh-secret-alias' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                              </Button>
                            </div>
                          </div>
                          <div>
                            <Label className="text-xs font-semibold mb-1 block">4. Add key password:</Label>
                            <div className="flex items-center gap-2">
                              <code className="text-xs flex-1 bg-background p-2 rounded break-all">
                                {`gh secret set ANDROID_KEY_ALIAS_PASSWORD --repo ${githubRepo || '<owner>/<repo-name>'} --body "YOUR_KEY_PASSWORD"`}
                              </code>
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                onClick={() => copyToClipboard(`gh secret set ANDROID_KEY_ALIAS_PASSWORD --repo ${githubRepo || '<owner>/<repo-name>'} --body "YOUR_KEY_PASSWORD"`, 'gh-secret-keypass')}
                              >
                                {copied === 'gh-secret-keypass' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                              </Button>
                            </div>
                          </div>
                          <div>
                            <Label className="text-xs font-semibold mb-1 block">5. Add backend URL:</Label>
                            <Collapsible className="mb-2">
                              <CollapsibleTrigger className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
                                <HelpCircle className="h-3 w-3" />
                                How to find your Replit deployment URL
                                <ChevronDown className="h-3 w-3" />
                              </CollapsibleTrigger>
                              <CollapsibleContent className="mt-2 text-xs text-muted-foreground space-y-2 pl-4 border-l-2 border-muted">
                                <p><strong>Option 1: From Replit Deploy tab</strong></p>
                                <ol className="list-decimal list-inside space-y-1 ml-2">
                                  <li>Click the <strong>"Deploy"</strong> button in the top right of Replit</li>
                                  <li>If already deployed, you'll see your deployment URL displayed</li>
                                  <li>It will look like: <code className="bg-background px-1 py-0.5 rounded">https://your-repl-name.replit.app</code> or <code className="bg-background px-1 py-0.5 rounded">https://xxx-xxx-xxx.replit.dev</code></li>
                                </ol>
                                <p className="mt-2"><strong>Option 2: From Replit URL bar</strong></p>
                                <p className="ml-2">If your Repl is deployed, check the URL in your browser's address bar when viewing the deployed app.</p>
                                <p className="mt-2"><strong>Option 3: From environment variables</strong></p>
                                <p className="ml-2">In Replit Shell, run: <code className="bg-background px-1 py-0.5 rounded">echo $REPLIT_DOMAINS</code></p>
                                <p className="text-xs mt-2 italic">Note: Use the production URL (ends in .replit.app or .replit.dev), not the development URL.</p>
                              </CollapsibleContent>
                            </Collapsible>
                            <div className="flex items-center gap-2">
                              <code className="text-xs flex-1 bg-background p-2 rounded break-all">
                                {`gh secret set BACKEND_URL --repo ${githubRepo || '<owner>/<repo-name>'} --body "https://your-repl-url.repl.co"`}
                              </code>
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                onClick={() => copyToClipboard(`gh secret set BACKEND_URL --repo ${githubRepo || '<owner>/<repo-name>'} --body "https://your-repl-url.repl.co"`, 'gh-secret-backend')}
                              >
                                {copied === 'gh-secret-backend' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                              </Button>
                            </div>
                            <p className="text-xs text-muted-foreground mt-1">
                              Replace <code className="bg-background px-1 py-0.5 rounded">https://your-repl-url.repl.co</code> with your actual Replit deployment URL (see instructions above).
                            </p>
                          </div>
                          <div>
                            <Label className="text-xs font-semibold mb-1 block">6. Add admin key:</Label>
                            <div className="flex items-center gap-2">
                              <code className="text-xs flex-1 bg-background p-2 rounded break-all">
                                {`gh secret set ADMIN_KEY --repo ${githubRepo || '<owner>/<repo-name>'} --body "YOUR_ADMIN_KEY"`}
                              </code>
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                onClick={() => copyToClipboard(`gh secret set ADMIN_KEY --repo ${githubRepo || '<owner>/<repo-name>'} --body "YOUR_ADMIN_KEY"`, 'gh-secret-admin')}
                              >
                                {copied === 'gh-secret-admin' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                              </Button>
                            </div>
                            <p className="text-xs text-muted-foreground mt-1">
                              Use the same ADMIN_KEY value you added to Replit Secrets earlier.
                            </p>
                          </div>
                        </div>
                      </div>

                      <div>
                        <h3 className="font-semibold mb-2">Step 6: Clone Repository and Setup Workflow</h3>
                        <p className="text-sm text-muted-foreground mb-2">
                          Clone your repository and add the GitHub Actions workflow file:
                        </p>
                        <div className="bg-muted p-4 rounded-md space-y-3">
                          <div>
                            <Label className="text-xs font-semibold mb-1 block">1. Clone your repository:</Label>
                            <div className="flex items-center gap-2">
                              <code className="text-xs flex-1 bg-background p-2 rounded break-all">
                                {`gh repo clone ${githubRepo || '<your-username>/<repo-name>'}`}
                              </code>
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                onClick={() => copyToClipboard(`gh repo clone ${githubRepo || '<your-username>/<repo-name>'}`, 'gh-clone')}
                              >
                                {copied === 'gh-clone' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                              </Button>
                            </div>
                            {!githubRepo && (
                              <p className="text-xs text-yellow-600 dark:text-yellow-400 mt-1">
                                ⚠️ Enter your repository name above to use the correct repository
                              </p>
                            )}
                          </div>
                          <div>
                            <Label className="text-xs font-semibold mb-1 block">2. Create GitHub Actions workflow directory:</Label>
                            <div className="flex items-center gap-2">
                              <code className="text-xs flex-1 bg-background p-2 rounded">
                                mkdir -p .github/workflows
                              </code>
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                onClick={() => copyToClipboard('mkdir -p .github/workflows', 'gh-mkdir')}
                              >
                                {copied === 'gh-mkdir' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                              </Button>
                            </div>
                          </div>
                          <div>
                            <Label className="text-xs font-semibold mb-1 block">3. Check if workflow file exists:</Label>
                            <p className="text-xs text-muted-foreground mb-2">
                              If you're remixing this project, the workflow file might already exist. Check first:
                            </p>
                            <div className="flex items-center gap-2 mb-3">
                              <code className="text-xs flex-1 bg-background p-2 rounded">
                                ls -la .github/workflows/android-build-and-deploy.yml
                              </code>
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                onClick={() => copyToClipboard('ls -la .github/workflows/android-build-and-deploy.yml', 'gh-check-workflow')}
                              >
                                {copied === 'gh-check-workflow' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                              </Button>
                            </div>
                            <Alert className="border-blue-500/50 bg-blue-50 dark:bg-blue-950/20 mb-3">
                              <Info className="h-4 w-4 text-blue-600 dark:text-blue-400" />
                              <AlertDescription className="text-blue-800 dark:text-blue-300 text-xs">
                                <strong>If the file exists:</strong> You're done! The workflow file is already set up. Skip to the next step.
                                <br />
                                <strong>If the file doesn't exist:</strong> Continue with step 4 below to create it.
                              </AlertDescription>
                            </Alert>
                          </div>
                          <div>
                            <Label className="text-xs font-semibold mb-1 block">4. Create workflow file (if it doesn't exist):</Label>
                            <p className="text-xs text-muted-foreground mb-2">
                              Copy the workflow file from the original repository or create it manually:
                            </p>
                            <div className="space-y-3">
                              <div>
                                <p className="text-xs font-semibold mb-1">Option A: Copy from original repo (recommended if remixing):</p>
                                <div className="flex items-center gap-2">
                                  <code className="text-xs flex-1 bg-background p-2 rounded break-all">
                                    curl -o .github/workflows/android-build-and-deploy.yml https://raw.githubusercontent.com/sergiogordon/unitymdm-prod/main/.github/workflows/android-build-and-deploy.yml
                                  </code>
                                  <Button
                                    type="button"
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => copyToClipboard('curl -o .github/workflows/android-build-and-deploy.yml https://raw.githubusercontent.com/sergiogordon/unitymdm-prod/main/.github/workflows/android-build-and-deploy.yml', 'gh-copy-workflow')}
                                  >
                                    {copied === 'gh-copy-workflow' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                                  </Button>
                                </div>
                              </div>
                              <div>
                                <p className="text-xs font-semibold mb-1">Option B: Create manually with an editor:</p>
                                <div className="flex items-center gap-2">
                                  <code className="text-xs flex-1 bg-background p-2 rounded">
                                    nano .github/workflows/android-build-and-deploy.yml
                                  </code>
                                  <Button
                                    type="button"
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => copyToClipboard('nano .github/workflows/android-build-and-deploy.yml', 'gh-nano-workflow')}
                                  >
                                    {copied === 'gh-nano-workflow' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                                  </Button>
                                </div>
                                <p className="text-xs text-muted-foreground mt-1">
                                  Then paste the workflow content. You can view it at: <a href="https://github.com/sergiogordon/unitymdm-prod/blob/main/.github/workflows/android-build-and-deploy.yml" target="_blank" rel="noopener noreferrer" className="text-primary underline">github.com/sergiogordon/unitymdm-prod/.github/workflows/android-build-and-deploy.yml</a>
                                </p>
                              </div>
                            </div>
                            <p className="text-xs text-muted-foreground mt-2">
                              <strong>Note:</strong> Make sure to update the secret names in the workflow file if they differ:
                              <br />
                              - <code className="bg-background px-1 py-0.5 rounded">NEXMDM_BACKEND_URL</code> (should match your <code className="bg-background px-1 py-0.5 rounded">BACKEND_URL</code> secret)
                              <br />
                              - <code className="bg-background px-1 py-0.5 rounded">NEXMDM_ADMIN_KEY</code> (should match your <code className="bg-background px-1 py-0.5 rounded">ADMIN_KEY</code> secret)
                            </p>
                          </div>
                        </div>
                      </div>
                    </>
                  )}

                  {skipGitHubCI && (
                    <Alert className="border-yellow-500/50 bg-yellow-50 dark:bg-yellow-950/20">
                      <AlertCircle className="h-4 w-4 text-yellow-600 dark:text-yellow-400" />
                      <AlertDescription className="text-yellow-800 dark:text-yellow-300 text-sm">
                        You've chosen to skip GitHub CI/CD setup. You'll need to build APKs manually using Android Studio. 
                        You can configure GitHub Actions later if needed.
                      </AlertDescription>
                    </Alert>
                  )}
                </div>

                <div className="flex gap-2">
                  <Button variant="outline" onClick={() => handleStepChange(3)}>
                    <ArrowLeft className="mr-2 h-4 w-4" /> Back
                  </Button>
                  {skipGitHubCI ? (
                    <Button
                      onClick={() => {
                        setShowGitHub(true)
                        handleStepChange(5) // Go to Discord step
                      }}
                      variant="outline"
                      className="flex-1"
                    >
                      Skip (Not Recommended) <ArrowRight className="ml-2 h-4 w-4" />
                    </Button>
                  ) : (
                    <Button
                      onClick={() => {
                        setShowGitHub(true)
                        handleStepChange(5) // Go to Discord step
                      }}
                      className="flex-1"
                    >
                      Continue to Next Step <ArrowRight className="ml-2 h-4 w-4" />
                    </Button>
                  )}
                </div>
              </div>
            )}

            {/* Step 5: Discord Webhook (Optional) */}
            {currentStep === 5 && (
              <div className="space-y-6">
                <Alert className="border-blue-500/50 bg-blue-50 dark:bg-blue-950/20">
                  <Info className="h-4 w-4 text-blue-600 dark:text-blue-400" />
                  <AlertDescription className="text-blue-800 dark:text-blue-300">
                    <strong>Optional:</strong> Discord webhooks allow you to receive alerts and notifications in your Discord server. 
                    This is useful for monitoring device status, alerts, and system events.
                  </AlertDescription>
                </Alert>

                {/* Current Discord Status */}
                {status && status.optional.discord_webhook && (
                  <div className="space-y-3">
                    {status.optional.discord_webhook.configured ? (
                      <Alert className="border-green-500/50 bg-green-50 dark:bg-green-950/20">
                        <CheckCircle2 className="h-5 w-5 text-green-600 dark:text-green-400" />
                        <AlertDescription className="text-green-800 dark:text-green-300">
                          <div className="flex items-center justify-between">
                            <div>
                              <strong>Discord webhook configured!</strong>
                              <p className="text-sm mt-1">{status.optional.discord_webhook.message}</p>
                            </div>
                            <Badge variant="outline" className="bg-green-100 dark:bg-green-900">
                              Configured
                            </Badge>
                          </div>
                        </AlertDescription>
                      </Alert>
                    ) : (
                      <Alert className="border-yellow-500/50 bg-yellow-50 dark:bg-yellow-950/20">
                        <AlertCircle className="h-5 w-5 text-yellow-600 dark:text-yellow-500" />
                        <AlertDescription className="text-yellow-800 dark:text-yellow-300">
                          <strong>Discord webhook not configured</strong>
                          <p className="text-sm mt-1">You can skip this step if you don't need Discord notifications.</p>
                        </AlertDescription>
                      </Alert>
                    )}
                  </div>
                )}

                <div className="space-y-4">
                  <div>
                    <h3 className="font-semibold mb-2">How to create a Discord webhook:</h3>
                    <ol className="list-decimal list-inside space-y-2 text-sm text-muted-foreground mb-4">
                      <li>Open Discord and go to your server</li>
                      <li>Go to <strong>Server Settings</strong> → <strong>Integrations</strong> → <strong>Webhooks</strong></li>
                      <li>Click <strong>"New Webhook"</strong> or <strong>"Create Webhook"</strong></li>
                      <li>Give your webhook a name (e.g., "NexMDM Alerts")</li>
                      <li>Choose which channel the webhook should post to</li>
                      <li>Click <strong>"Copy Webhook URL"</strong></li>
                      <li>Paste the URL below</li>
                    </ol>
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label htmlFor="discord-webhook">DISCORD_WEBHOOK_URL</Label>
                      <Badge variant={status?.optional.discord_webhook?.configured ? "default" : "outline"}>
                        {status?.optional.discord_webhook?.configured ? "Configured" : "Optional"}
                      </Badge>
                    </div>
                    <Input
                      id="discord-webhook"
                      value={discordWebhookUrl}
                      onChange={(e) => setDiscordWebhookUrl(e.target.value)}
                      placeholder="https://discord.com/api/webhooks/..."
                      className="font-mono text-sm"
                    />
                    {discordWebhookUrl && !discordWebhookUrl.startsWith('https://discord.com/api/webhooks/') && (
                      <Alert className="border-red-500/50 bg-red-50 dark:bg-red-950/20">
                        <XCircle className="h-4 w-4 text-red-600 dark:text-red-400" />
                        <AlertDescription className="text-red-800 dark:text-red-300 text-sm">
                          Discord webhook URLs must start with <code>https://discord.com/api/webhooks/</code>
                        </AlertDescription>
                      </Alert>
                    )}
                    {discordWebhookUrl && discordWebhookUrl.startsWith('https://discord.com/api/webhooks/') && (
                      <div className="bg-muted p-4 rounded-md">
                        <p className="text-sm font-mono mb-2">Add to Replit Secrets:</p>
                        <div className="flex items-center gap-2">
                          <code className="text-xs flex-1 bg-background p-2 rounded break-all">
                            DISCORD_WEBHOOK_URL={discordWebhookUrl}
                          </code>
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            onClick={() => copyToClipboard(`DISCORD_WEBHOOK_URL=${discordWebhookUrl}`, 'discord-webhook-full')}
                          >
                            {copied === 'discord-webhook-full' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                <div className="flex gap-2">
                  <Button variant="outline" onClick={() => handleStepChange(4)}>
                    <ArrowLeft className="mr-2 h-4 w-4" /> Back to GitHub
                  </Button>
                  <Button
                    onClick={async () => {
                      setChecking(true)
                      await checkSetupStatus()
                      setChecking(false)
                      handleStepChange(6) // Go to Keystore step
                    }}
                    disabled={checking}
                    className="flex-1"
                  >
                    {checking ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Checking...
                      </>
                    ) : (
                      <>
                        Continue <ArrowRight className="ml-2 h-4 w-4" />
                      </>
                    )}
                  </Button>
                </div>
              </div>
            )}

            {/* Step 6: Android Keystore (Optional) */}
            {currentStep === 6 && (
              <div className="space-y-6">
                <Alert className="border-blue-500/50 bg-blue-50 dark:bg-blue-950/20">
                  <Info className="h-4 w-4 text-blue-600 dark:text-blue-400" />
                  <AlertDescription className="text-blue-800 dark:text-blue-300">
                    <strong>Optional:</strong> Android keystore is only needed if you plan to build and sign Android APKs. 
                    You can skip this step if you're not building Android apps.
                  </AlertDescription>
                </Alert>

                <div className="space-y-4">
                  <p className="text-sm text-muted-foreground">
                    The Android keystore is used to sign your APK files. If you're using GitHub Actions CI/CD (configured in the previous step), 
                    you'll need to add the keystore as a GitHub secret. Otherwise, you can add it directly to Replit Secrets.
                  </p>
                  
                  <Alert>
                    <AlertDescription className="text-sm">
                      <strong>Note:</strong> Keystore setup instructions are included in the GitHub CI/CD step. 
                      If you've already configured GitHub Actions, you can skip this step.
                    </AlertDescription>
                  </Alert>
                </div>

                <div className="flex gap-2">
                  <Button variant="outline" onClick={() => handleStepChange(5)}>
                    <ArrowLeft className="mr-2 h-4 w-4" /> Back
                  </Button>
                  <Button
                    onClick={() => handleStepChange(7)} // Go to Complete step
                    className="flex-1"
                  >
                    Skip Keystore <ArrowRight className="ml-2 h-4 w-4" />
                  </Button>
                  <Button
                    onClick={() => handleStepChange(7)} // Go to Complete step
                    className="flex-1"
                  >
                    Continue <ArrowRight className="ml-2 h-4 w-4" />
                  </Button>
                </div>
              </div>
            )}

            {/* Step 7: Setup Complete */}
            {currentStep === 7 && (
              <div className="space-y-6">
                <div className="text-center">
                  <CheckCircle2 className="h-16 w-16 text-green-500 mx-auto mb-4" />
                  <h2 className="text-2xl font-bold mb-2">Setup Complete!</h2>
                  <p className="text-muted-foreground mb-6">
                    All required configuration is complete. You can now use NexMDM.
                  </p>
                </div>

                {/* Backend Status Indicator */}
                <Card className="border-2">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-lg flex items-center gap-2">
                      <Settings className="h-5 w-5" />
                      Backend Server Status
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {checkingBackend && !backendHealth && (
                      <div className="flex items-center gap-3 text-muted-foreground">
                        <Loader2 className="h-5 w-5 animate-spin" />
                        <span>Checking backend status...</span>
                      </div>
                    )}

                    {backendHealth && (
                      <div className="space-y-3">
                        {backendHealth.status === 'running' && (
                          <Alert className="border-green-500/50 bg-green-50 dark:bg-green-950/20">
                            <CheckCircle2 className="h-5 w-5 text-green-600 dark:text-green-400" />
                            <AlertDescription className="text-green-800 dark:text-green-300">
                              <div className="flex items-center justify-between">
                                <div>
                                  <strong>Backend is running!</strong>
                                  {backendHealth.details?.uptime_formatted && (
                                    <p className="text-sm mt-1">
                                      Uptime: {backendHealth.details.uptime_formatted}
                                    </p>
                                  )}
                                </div>
                                <Badge variant="outline" className="bg-green-100 dark:bg-green-900">
                                  Online
                                </Badge>
                              </div>
                            </AlertDescription>
                          </Alert>
                        )}

                        {backendHealth.status === 'not_running' && (
                          <Alert className="border-yellow-500/50 bg-yellow-50 dark:bg-yellow-950/20">
                            <AlertCircle className="h-5 w-5 text-yellow-600 dark:text-yellow-400" />
                            <AlertDescription className="text-yellow-800 dark:text-yellow-300">
                              <div className="space-y-3">
                                <div className="flex items-center justify-between">
                                  <div>
                                    <strong>Backend server is not running</strong>
                                    <p className="text-sm mt-1">
                                      {backendHealth.message}
                                    </p>
                                  </div>
                                  <Badge variant="outline" className="bg-yellow-100 dark:bg-yellow-900">
                                    Offline
                                  </Badge>
                                </div>
                                
                                <div className="bg-background p-3 rounded-md border">
                                  <p className="text-sm font-semibold mb-2">To start the backend:</p>
                                  <ol className="list-decimal list-inside text-sm space-y-1 text-muted-foreground">
                                    <li>Click the <strong>"Run"</strong> button at the top of Replit</li>
                                    <li>Wait for the backend to start (check the console for startup messages)</li>
                                    <li>Click "Check Status" below to verify</li>
                                  </ol>
                                </div>

                                {pollingBackend && (
                                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                    <span>Automatically checking for backend startup...</span>
                                  </div>
                                )}
                              </div>
                            </AlertDescription>
                          </Alert>
                        )}

                        {backendHealth.status === 'error' && (
                          <Alert className="border-red-500/50 bg-red-50 dark:bg-red-950/20">
                            <XCircle className="h-5 w-5 text-red-600 dark:text-red-400" />
                            <AlertDescription className="text-red-800 dark:text-red-300">
                              <div className="flex items-center justify-between">
                                <div>
                                  <strong>Error checking backend</strong>
                                  <p className="text-sm mt-1">
                                    {backendHealth.message}
                                  </p>
                                </div>
                                <Badge variant="outline" className="bg-red-100 dark:bg-red-900">
                                  Error
                                </Badge>
                              </div>
                            </AlertDescription>
                          </Alert>
                        )}
                      </div>
                    )}

                    <div className="flex gap-2">
                      <Button
                        onClick={checkBackendHealthStatus}
                        variant="outline"
                        disabled={checkingBackend || pollingBackend}
                        className="flex-1"
                      >
                        {checkingBackend ? (
                          <>
                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            Checking...
                          </>
                        ) : (
                          <>
                            <Settings className="mr-2 h-4 w-4" />
                            Check Status
                          </>
                        )}
                      </Button>
                      {backendHealth?.status === 'not_running' && !pollingBackend && (
                        <Button
                          onClick={startBackendPolling}
                          variant="outline"
                          className="flex-1"
                        >
                          <Loader2 className="mr-2 h-4 w-4" />
                          Auto-Check
                        </Button>
                      )}
                    </div>
                  </CardContent>
                </Card>

                {/* Database Status Indicator */}
                <Card className="border-2">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-lg flex items-center gap-2">
                      <Shield className="h-5 w-5" />
                      Database Status
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {status && status.required.database && (
                      <div className="space-y-3">
                        {status.required.database.configured && status.required.database.valid && (
                          <Alert className="border-green-500/50 bg-green-50 dark:bg-green-950/20">
                            <CheckCircle2 className="h-5 w-5 text-green-600 dark:text-green-400" />
                            <AlertDescription className="text-green-800 dark:text-green-300">
                              <div className="flex items-center justify-between">
                                <div>
                                  <strong>Database configured and connected!</strong>
                                  <p className="text-sm mt-1">
                                    {status.required.database.type && (
                                      <span className="capitalize">{status.required.database.type}</span>
                                    )} {status.required.database.message}
                                  </p>
                                </div>
                                <Badge variant="outline" className="bg-green-100 dark:bg-green-900">
                                  Connected
                                </Badge>
                              </div>
                            </AlertDescription>
                          </Alert>
                        )}

                        {status.required.database.configured && !status.required.database.valid && (
                          <Alert className="border-red-500/50 bg-red-50 dark:bg-red-950/20">
                            <XCircle className="h-5 w-5 text-red-600 dark:text-red-400" />
                            <AlertDescription className="text-red-800 dark:text-red-300">
                              <div className="space-y-3">
                                <div className="flex items-center justify-between">
                                  <div>
                                    <strong>Database connection failed</strong>
                                    <p className="text-sm mt-1">
                                      {status.required.database.message}
                                    </p>
                                  </div>
                                  <Badge variant="outline" className="bg-red-100 dark:bg-red-900">
                                    Error
                                  </Badge>
                                </div>
                                
                                <div className="bg-background p-3 rounded-md border">
                                  <p className="text-sm font-semibold mb-2">Troubleshooting:</p>
                                  <ul className="list-disc list-inside text-sm space-y-1 text-muted-foreground">
                                    <li>Verify DATABASE_URL is correct in Replit Secrets</li>
                                    <li>Check that PostgreSQL integration is set up in Replit</li>
                                    <li>Ensure database server is running and accessible</li>
                                    <li>Restart backend after updating DATABASE_URL</li>
                                  </ul>
                                </div>
                              </div>
                            </AlertDescription>
                          </Alert>
                        )}

                        {!status.required.database.configured && (
                          <Alert className="border-yellow-500/50 bg-yellow-50 dark:bg-yellow-950/20">
                            <AlertCircle className="h-5 w-5 text-yellow-600 dark:text-yellow-400" />
                            <AlertDescription className="text-yellow-800 dark:text-yellow-300">
                              <div className="space-y-3">
                                <div className="flex items-center justify-between">
                                  <div>
                                    <strong>Using default SQLite database</strong>
                                    <p className="text-sm mt-1">
                                      {status.required.database.message}
                                    </p>
                                  </div>
                                  <Badge variant="outline" className="bg-yellow-100 dark:bg-yellow-900">
                                    Default
                                  </Badge>
                                </div>
                                
                                <div className="bg-background p-3 rounded-md border">
                                  <p className="text-sm font-semibold mb-2">To set up PostgreSQL (recommended):</p>
                                  <ol className="list-decimal list-inside text-sm space-y-1 text-muted-foreground">
                                    <li>Click <strong>Tools</strong> (🔧) in the Replit sidebar</li>
                                    <li>Click <strong>Add Integration</strong> → Search "PostgreSQL"</li>
                                    <li>Click <strong>Set up</strong> to create your database</li>
                                    <li>Replit will automatically set DATABASE_URL</li>
                                    <li>Restart the backend to use PostgreSQL</li>
                                  </ol>
                                  <p className="text-xs text-muted-foreground mt-2">
                                    Note: SQLite works for development, but PostgreSQL is recommended for production deployments.
                                  </p>
                                </div>
                              </div>
                            </AlertDescription>
                          </Alert>
                        )}
                      </div>
                    )}

                    {databaseTestResult && (
                      <Alert className={databaseTestResult.connected 
                        ? "border-green-500/50 bg-green-50 dark:bg-green-950/20"
                        : "border-red-500/50 bg-red-50 dark:bg-red-950/20"
                      }>
                        {databaseTestResult.connected ? (
                          <CheckCircle2 className="h-5 w-5 text-green-600 dark:text-green-400" />
                        ) : (
                          <XCircle className="h-5 w-5 text-red-600 dark:text-red-400" />
                        )}
                        <AlertDescription className={databaseTestResult.connected
                          ? "text-green-800 dark:text-green-300"
                          : "text-red-800 dark:text-red-300"
                        }>
                          <strong>{databaseTestResult.connected ? 'Connection successful!' : 'Connection failed'}</strong>
                          <p className="text-sm mt-1">{databaseTestResult.message}</p>
                          {databaseTestResult.type && (
                            <p className="text-xs mt-1">Database type: {databaseTestResult.type}</p>
                          )}
                        </AlertDescription>
                      </Alert>
                    )}

                    <Button
                      onClick={testDatabaseConnection}
                      variant="outline"
                      disabled={testingDatabase}
                      className="w-full"
                    >
                      {testingDatabase ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          Testing Connection...
                        </>
                      ) : (
                        <>
                          <Shield className="mr-2 h-4 w-4" />
                          Test Database Connection
                        </>
                      )}
                    </Button>
                  </CardContent>
                </Card>

                {/* Object Storage Status Indicator */}
                {status && status.optional.object_storage && (
                  <Card className="border-2">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-lg flex items-center gap-2">
                        <Cloud className="h-5 w-5" />
                        Object Storage Status
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      {status.optional.object_storage.configured && status.optional.object_storage.available && (
                        <Alert className="border-green-500/50 bg-green-50 dark:bg-green-950/20">
                          <CheckCircle2 className="h-5 w-5 text-green-600 dark:text-green-400" />
                          <AlertDescription className="text-green-800 dark:text-green-300">
                            <div className="flex items-center justify-between">
                              <div>
                                <strong>Object Storage available!</strong>
                                <p className="text-sm mt-1">
                                  {status.optional.object_storage.message}
                                </p>
                              </div>
                              <Badge variant="outline" className="bg-green-100 dark:bg-green-900">
                                Available
                              </Badge>
                            </div>
                          </AlertDescription>
                        </Alert>
                      )}

                      {status.optional.object_storage.configured && !status.optional.object_storage.available && (
                        <Alert className="border-red-500/50 bg-red-50 dark:bg-red-950/20">
                          <XCircle className="h-5 w-5 text-red-600 dark:text-red-400" />
                          <AlertDescription className="text-red-800 dark:text-red-300">
                            <div className="space-y-3">
                              <div className="flex items-center justify-between">
                                <div>
                                  <strong>Object Storage not accessible</strong>
                                  <p className="text-sm mt-1">
                                    {status.optional.object_storage.message}
                                  </p>
                                </div>
                                <Badge variant="outline" className="bg-red-100 dark:bg-red-900">
                                  Error
                                </Badge>
                              </div>
                              
                              <div className="bg-background p-3 rounded-md border">
                                <p className="text-sm font-semibold mb-2">Troubleshooting:</p>
                                <ul className="list-disc list-inside text-sm space-y-1 text-muted-foreground">
                                  <li>Verify Object Storage integration is set up in Replit</li>
                                  <li>Check that the default bucket is accessible</li>
                                  <li>Restart backend after setting up Object Storage</li>
                                </ul>
                              </div>
                            </div>
                          </AlertDescription>
                        </Alert>
                      )}

                      {!status.optional.object_storage.configured && (
                        <Alert className="border-yellow-500/50 bg-yellow-50 dark:bg-yellow-950/20">
                          <AlertCircle className="h-5 w-5 text-yellow-600 dark:text-yellow-400" />
                          <AlertDescription className="text-yellow-800 dark:text-yellow-300">
                            <div className="space-y-3">
                              <div className="flex items-center justify-between">
                                <div>
                                  <strong>Object Storage not configured</strong>
                                  <p className="text-sm mt-1">
                                    {status.optional.object_storage.message}
                                  </p>
                                </div>
                                <Badge variant="outline" className="bg-yellow-100 dark:bg-yellow-900">
                                  Required
                                </Badge>
                              </div>
                              
                              <div className="bg-background p-3 rounded-md border">
                                <p className="text-sm font-semibold mb-2">To set up Object Storage (required for APK storage):</p>
                                <ol className="list-decimal list-inside text-sm space-y-1 text-muted-foreground">
                                  <li>Click <strong>Tools</strong> (🔧) in the Replit sidebar</li>
                                  <li>Click <strong>Add Integration</strong> → Search "Object Storage"</li>
                                  <li>Click <strong>Set up</strong> to enable storage</li>
                                  <li>Restart the backend to use Object Storage</li>
                                </ol>
                                <p className="text-xs text-muted-foreground mt-2">
                                  Note: Object Storage is required for uploading and storing Android APK files.
                                </p>
                              </div>
                            </div>
                          </AlertDescription>
                        </Alert>
                      )}
                    </CardContent>
                  </Card>
                )}

                {/* Email Service Status Indicator */}
                {status && status.optional.email_service && (
                  <Card className="border-2">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-lg flex items-center gap-2">
                        <Mail className="h-5 w-5" />
                        Email Service Status
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      {status.optional.email_service.configured && status.optional.email_service.available && (
                        <Alert className="border-green-500/50 bg-green-50 dark:bg-green-950/20">
                          <CheckCircle2 className="h-5 w-5 text-green-600 dark:text-green-400" />
                          <AlertDescription className="text-green-800 dark:text-green-300">
                            <div className="flex items-center justify-between">
                              <div>
                                <strong>ReplitMail available!</strong>
                                <p className="text-sm mt-1">
                                  {status.optional.email_service.message}
                                </p>
                              </div>
                              <Badge variant="outline" className="bg-green-100 dark:bg-green-900">
                                Available
                              </Badge>
                            </div>
                          </AlertDescription>
                        </Alert>
                      )}

                      {status.optional.email_service.configured && !status.optional.email_service.available && (
                        <Alert className="border-red-500/50 bg-red-50 dark:bg-red-950/20">
                          <XCircle className="h-5 w-5 text-red-600 dark:text-red-400" />
                          <AlertDescription className="text-red-800 dark:text-red-300">
                            <div className="space-y-3">
                              <div className="flex items-center justify-between">
                                <div>
                                  <strong>Email service not accessible</strong>
                                  <p className="text-sm mt-1">
                                    {status.optional.email_service.message}
                                  </p>
                                </div>
                                <Badge variant="outline" className="bg-red-100 dark:bg-red-900">
                                  Error
                                </Badge>
                              </div>
                              
                              <div className="bg-background p-3 rounded-md border">
                                <p className="text-sm font-semibold mb-2">Troubleshooting:</p>
                                <ul className="list-disc list-inside text-sm space-y-1 text-muted-foreground">
                                  <li>Verify ReplitMail integration is set up in Replit</li>
                                  <li>Check that REPL_IDENTITY or WEB_REPL_RENEWAL is set</li>
                                  <li>Restart backend after setting up ReplitMail</li>
                                </ul>
                              </div>
                            </div>
                          </AlertDescription>
                        </Alert>
                      )}

                      {!status.optional.email_service.configured && (
                        <Alert className="border-blue-500/50 bg-blue-50 dark:bg-blue-950/20">
                          <Info className="h-5 w-5 text-blue-600 dark:text-blue-400" />
                          <AlertDescription className="text-blue-800 dark:text-blue-300">
                            <div className="space-y-3">
                              <div className="flex items-center justify-between">
                                <div>
                                  <strong>Email service not configured</strong>
                                  <p className="text-sm mt-1">
                                    {status.optional.email_service.message}
                                  </p>
                                </div>
                                <Badge variant="outline" className="bg-blue-100 dark:bg-blue-900">
                                  Optional
                                </Badge>
                              </div>
                              
                              <div className="bg-background p-3 rounded-md border">
                                <p className="text-sm font-semibold mb-2">To set up ReplitMail (recommended for email notifications):</p>
                                <ol className="list-decimal list-inside text-sm space-y-1 text-muted-foreground">
                                  <li>Click <strong>Tools</strong> (🔧) in the Replit sidebar</li>
                                  <li>Click <strong>Add Integration</strong> → Search "ReplitMail"</li>
                                  <li>Click <strong>Set up</strong> to enable email service</li>
                                  <li>Restart the backend to use ReplitMail</li>
                                </ol>
                                <p className="text-xs text-muted-foreground mt-2">
                                  Note: Email service is optional but recommended for password reset emails and alerts.
                                </p>
                              </div>
                            </div>
                          </AlertDescription>
                        </Alert>
                      )}
                    </CardContent>
                  </Card>
                )}

                {/* Verification Steps */}
                <Collapsible>
                  <CollapsibleTrigger className="flex items-center justify-between w-full p-4 bg-muted rounded-md hover:bg-muted/80">
                    <div className="flex items-center gap-2">
                      <Info className="h-5 w-5 text-blue-600 dark:text-blue-400" />
                      <span className="font-semibold">Verify Your Setup</span>
                    </div>
                    <ChevronDown className="h-4 w-4" />
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    <div className="p-4 space-y-4 bg-muted/50 rounded-b-md">
                      <div>
                        <h4 className="font-semibold mb-2 text-sm">1. Check Backend Status</h4>
                        <p className="text-sm text-muted-foreground mb-2">
                          Verify that your backend is running and accessible:
                        </p>
                        <div className="flex items-center gap-2">
                          <code className="text-xs flex-1 bg-background p-2 rounded">
                            curl {typeof window !== 'undefined' ? window.location.origin : ''}/api/setup/status
                          </code>
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={() => copyToClipboard(`${typeof window !== 'undefined' ? window.location.origin : ''}/api/setup/status`, 'verify-backend')}
                          >
                            {copied === 'verify-backend' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                          </Button>
                        </div>
                        <p className="text-xs text-muted-foreground mt-1">
                          Or click the "Verify Configuration" button below to check automatically.
                        </p>
                      </div>
                      <div>
                        <h4 className="font-semibold mb-2 text-sm">2. Verify Secrets</h4>
                        <p className="text-sm text-muted-foreground mb-2">
                          Make sure all secrets are correctly added to Replit Secrets:
                        </p>
                        <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
                          <li><code className="bg-background px-1 py-0.5 rounded">ADMIN_KEY</code> - Should be at least 16 characters</li>
                          <li><code className="bg-background px-1 py-0.5 rounded">SESSION_SECRET</code> - Should be at least 32 characters</li>
                          <li><code className="bg-background px-1 py-0.5 rounded">FIREBASE_SERVICE_ACCOUNT_JSON</code> - Should be valid JSON</li>
                        </ul>
                      </div>
                      <div>
                        <h4 className="font-semibold mb-2 text-sm">3. Restart Backend (if needed)</h4>
                        <p className="text-sm text-muted-foreground">
                          If you just added secrets, restart your Repl backend to load the new environment variables.
                          Click the "Stop" button and then "Run" again in Replit.
                        </p>
                      </div>
                    </div>
                  </CollapsibleContent>
                </Collapsible>

                {/* Troubleshooting Section */}
                <Accordion type="single" collapsible>
                  <AccordionItem value="troubleshooting">
                    <AccordionTrigger className="flex items-center gap-2">
                      <HelpCircle className="h-5 w-5 text-muted-foreground" />
                      <span>Troubleshooting</span>
                    </AccordionTrigger>
                    <AccordionContent>
                      <div className="space-y-4 text-sm">
                        <div>
                          <h4 className="font-semibold mb-1">Backend not accessible</h4>
                          <ul className="list-disc list-inside text-muted-foreground space-y-1 ml-2">
                            <li>Check if backend is running in Replit (look for "Running" status)</li>
                            <li>Verify the backend URL is correct</li>
                            <li>Check Replit console for error messages</li>
                            <li>Try restarting the backend</li>
                          </ul>
                        </div>
                        <div>
                          <h4 className="font-semibold mb-1">Firebase validation fails</h4>
                          <ul className="list-disc list-inside text-muted-foreground space-y-1 ml-2">
                            <li>Ensure JSON is valid (no extra commas, proper quotes)</li>
                            <li>Check that all required fields are present: <code className="bg-background px-1 py-0.5 rounded">type</code>, <code className="bg-background px-1 py-0.5 rounded">project_id</code>, <code className="bg-background px-1 py-0.5 rounded">private_key</code>, <code className="bg-background px-1 py-0.5 rounded">client_email</code></li>
                            <li>Make sure you copied the entire JSON content, including opening and closing braces</li>
                            <li>Verify the JSON is pasted as a single-line string in Replit Secrets</li>
                          </ul>
                        </div>
                        <div>
                          <h4 className="font-semibold mb-1">GitHub CLI authentication fails</h4>
                          <ul className="list-disc list-inside text-muted-foreground space-y-1 ml-2">
                            <li>Re-run <code className="bg-background px-1 py-0.5 rounded">gh auth login</code></li>
                            <li>Choose "HTTPS" and "Login with a web browser"</li>
                            <li>Complete authentication in the browser window that opens</li>
                            <li>Verify with <code className="bg-background px-1 py-0.5 rounded">gh auth status</code></li>
                          </ul>
                        </div>
                        <div>
                          <h4 className="font-semibold mb-1">Secrets not working</h4>
                          <ul className="list-disc list-inside text-muted-foreground space-y-1 ml-2">
                            <li>Verify secret names match exactly (case-sensitive): <code className="bg-background px-1 py-0.5 rounded">ADMIN_KEY</code>, <code className="bg-background px-1 py-0.5 rounded">SESSION_SECRET</code>, etc.</li>
                            <li>Check for typos or extra spaces</li>
                            <li>Ensure secrets are added to the correct Replit Secrets tab</li>
                            <li>Restart backend after adding new secrets</li>
                          </ul>
                        </div>
                        <div>
                          <h4 className="font-semibold mb-1">Setup status shows "Not Ready"</h4>
                          <ul className="list-disc list-inside text-muted-foreground space-y-1 ml-2">
                            <li>Click "Verify Configuration" button to refresh status</li>
                            <li>Check that all required secrets are configured and valid</li>
                            <li>Review error messages in the setup status response</li>
                            <li>Ensure backend is running and accessible</li>
                          </ul>
                        </div>
                      </div>
                    </AccordionContent>
                  </AccordionItem>
                </Accordion>

                {/* End-to-End Verification */}
                <Card className="border-2 border-primary/20">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-lg flex items-center gap-2">
                      <CheckCircle2 className="h-5 w-5" />
                      System Verification
                    </CardTitle>
                    <CardDescription>
                      Test all critical components to ensure everything is working
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {verificationResult && (
                      <div className="space-y-3">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                          <div className={`p-3 rounded-md border ${verificationResult.backend.available ? 'bg-green-50 dark:bg-green-950/20 border-green-200 dark:border-green-800' : 'bg-red-50 dark:bg-red-950/20 border-red-200 dark:border-red-800'}`}>
                            <div className="flex items-center gap-2 mb-1">
                              {verificationResult.backend.available ? (
                                <CheckCircle2 className="h-4 w-4 text-green-600 dark:text-green-400" />
                              ) : (
                                <XCircle className="h-4 w-4 text-red-600 dark:text-red-400" />
                              )}
                              <span className="font-semibold text-sm">Backend</span>
                            </div>
                            <p className="text-xs text-muted-foreground">{verificationResult.backend.message}</p>
                          </div>

                          <div className={`p-3 rounded-md border ${verificationResult.database.available ? 'bg-green-50 dark:bg-green-950/20 border-green-200 dark:border-green-800' : 'bg-red-50 dark:bg-red-950/20 border-red-200 dark:border-red-800'}`}>
                            <div className="flex items-center gap-2 mb-1">
                              {verificationResult.database.available ? (
                                <CheckCircle2 className="h-4 w-4 text-green-600 dark:text-green-400" />
                              ) : (
                                <XCircle className="h-4 w-4 text-red-600 dark:text-red-400" />
                              )}
                              <span className="font-semibold text-sm">Database</span>
                            </div>
                            <p className="text-xs text-muted-foreground">{verificationResult.database.message}</p>
                          </div>

                          <div className={`p-3 rounded-md border ${verificationResult.object_storage.available ? 'bg-green-50 dark:bg-green-950/20 border-green-200 dark:border-green-800' : 'bg-red-50 dark:bg-red-950/20 border-red-200 dark:border-red-800'}`}>
                            <div className="flex items-center gap-2 mb-1">
                              {verificationResult.object_storage.available ? (
                                <CheckCircle2 className="h-4 w-4 text-green-600 dark:text-green-400" />
                              ) : (
                                <XCircle className="h-4 w-4 text-red-600 dark:text-red-400" />
                              )}
                              <span className="font-semibold text-sm">Object Storage</span>
                            </div>
                            <p className="text-xs text-muted-foreground">{verificationResult.object_storage.message}</p>
                          </div>

                          <div className={`p-3 rounded-md border ${verificationResult.signup_endpoint.available ? 'bg-green-50 dark:bg-green-950/20 border-green-200 dark:border-green-800' : 'bg-yellow-50 dark:bg-yellow-950/20 border-yellow-200 dark:border-yellow-800'}`}>
                            <div className="flex items-center gap-2 mb-1">
                              {verificationResult.signup_endpoint.available ? (
                                <CheckCircle2 className="h-4 w-4 text-green-600 dark:text-green-400" />
                              ) : (
                                <AlertCircle className="h-4 w-4 text-yellow-600 dark:text-yellow-400" />
                              )}
                              <span className="font-semibold text-sm">Signup Endpoint</span>
                            </div>
                            <p className="text-xs text-muted-foreground">{verificationResult.signup_endpoint.message}</p>
                          </div>
                        </div>

                        {verificationResult.all_ready && (
                          <Alert className="border-green-500/50 bg-green-50 dark:bg-green-950/20">
                            <CheckCircle2 className="h-5 w-5 text-green-600 dark:text-green-400" />
                            <AlertDescription className="text-green-800 dark:text-green-300">
                              <strong>All systems ready!</strong> Your NexMDM instance is fully configured and ready to use.
                            </AlertDescription>
                          </Alert>
                        )}

                        {!verificationResult.all_ready && (
                          <Alert className="border-yellow-500/50 bg-yellow-50 dark:bg-yellow-950/20">
                            <AlertCircle className="h-5 w-5 text-yellow-600 dark:text-yellow-400" />
                            <AlertDescription className="text-yellow-800 dark:text-yellow-300">
                              <strong>Some components need attention.</strong> Please fix the issues above before proceeding to signup.
                            </AlertDescription>
                          </Alert>
                        )}
                      </div>
                    )}

                    <Button
                      onClick={verifyEverything}
                      variant="default"
                      disabled={verifying}
                      className="w-full"
                    >
                      {verifying ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          Verifying...
                        </>
                      ) : (
                        <>
                          <CheckCircle2 className="mr-2 h-4 w-4" />
                          Verify Everything Works
                        </>
                      )}
                    </Button>
                  </CardContent>
                </Card>

                {/* What's Next Section */}
                <Alert className="border-green-500/50 bg-green-50 dark:bg-green-950/20">
                  <Info className="h-4 w-4 text-green-600 dark:text-green-400" />
                  <AlertDescription className="text-green-800 dark:text-green-300">
                    <strong>What's Next:</strong>
                    <ol className="list-decimal list-inside mt-2 space-y-2 text-sm">
                      <li>
                        <strong>Verify your configuration:</strong> Click "Verify Configuration" below to ensure all secrets are properly set up
                      </li>
                      <li>
                        <strong>Restart your Repl:</strong> If you just added secrets, stop and restart your Repl backend to load the new environment variables
                      </li>
                      <li>
                        <strong>Create your admin account:</strong> Click "Go to Signup" to create your first admin user account
                      </li>
                      <li>
                        <strong>Start enrolling devices:</strong> Once logged in, you can begin enrolling Android devices to your MDM system
                      </li>
                      <li>
                        <strong>Configure GitHub CI/CD (optional):</strong> If you skipped GitHub setup earlier, you can set it up later when your Android project is ready
                      </li>
                    </ol>
                  </AlertDescription>
                </Alert>

                <div className="flex gap-2">
                  <Button
                    onClick={async () => {
                      setChecking(true)
                      await checkSetupStatus()
                      setChecking(false)
                    }}
                    variant="outline"
                    disabled={checking}
                    className="flex-1"
                  >
                    {checking ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Verifying...
                      </>
                    ) : (
                      <>
                        <CheckCircle2 className="mr-2 h-4 w-4" />
                        Verify Configuration
                      </>
                    )}
                  </Button>
                  <Button
                    onClick={() => {
                      // Mark setup as complete in sessionStorage before navigating
                      // This ensures SetupCheck allows signup page to proceed
                      sessionStorage.setItem('setup_checked', 'ready')
                      localStorage.removeItem('setup_step')
                      router.push('/signup')
                    }}
                    className="flex-1"
                  >
                    Go to Signup <ArrowRight className="ml-2 h-4 w-4" />
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

