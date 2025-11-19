"use client"

import { useState, useEffect } from "react"
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
  Info
} from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"

interface SetupStatus {
  required: {
    admin_key: { configured: boolean; valid: boolean; message: string }
    jwt_secret: { configured: boolean; valid: boolean; message: string }
    firebase: { configured: boolean; valid: boolean; message: string }
  }
  optional: {
    discord_webhook: { configured: boolean; message: string }
    github_ci: { configured: boolean; message: string }
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
  
  // Step 1: Admin Credentials
  const [adminKey, setAdminKey] = useState("")
  const [jwtSecret, setJwtSecret] = useState("")
  const [copied, setCopied] = useState<string | null>(null)
  
  // Step 2: Firebase
  const [firebaseJson, setFirebaseJson] = useState("")
  const [firebaseValidating, setFirebaseValidating] = useState(false)
  const [firebaseValid, setFirebaseValid] = useState<boolean | null>(null)
  const [firebaseMessage, setFirebaseMessage] = useState("")
  
  // Step 3: GitHub CI (optional)
  const [showGitHub, setShowGitHub] = useState(false)
  
  // Step 4: Keystore (optional)
  const [keystorePassword, setKeystorePassword] = useState("")
  const [keyPassword, setKeyPassword] = useState("")
  const [keyAlias, setKeyAlias] = useState("nexmdm")

  // Load saved progress from localStorage
  useEffect(() => {
    const savedStep = localStorage.getItem('setup_step')
    if (savedStep) {
      const step = parseInt(savedStep, 10)
      if (step >= 0 && step < steps.length) {
        setCurrentStep(step)
      }
    }
  }, [])

  useEffect(() => {
    checkSetupStatus()
  }, [])

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
      id: 'github',
      title: 'GitHub CI/CD (Optional)',
      icon: Github
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
                    <li>Admin API key and JWT secret</li>
                    <li>Firebase Cloud Messaging credentials</li>
                    <li>GitHub Actions secrets (optional, for Android CI/CD)</li>
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
                          <li><strong>Secret Name:</strong> Enter the exact name shown (e.g., <code>ADMIN_KEY</code> or <code>SESSION_SECRET</code>)</li>
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
                      if (adminKey && jwtSecret) {
                        handleStepChange(2)
                      } else {
                        toast.info("Please generate and add the secrets to Replit first")
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
                    <ol className="list-decimal list-inside space-y-1 text-sm text-muted-foreground">
                      <li>Go to <a href="https://console.firebase.google.com" target="_blank" rel="noopener noreferrer" className="text-primary underline">Firebase Console</a></li>
                      <li>Create a new project or select existing</li>
                      <li>Navigate to <strong>Project Settings</strong> → <strong>Service Accounts</strong></li>
                      <li>Click <strong>Generate New Private Key</strong></li>
                      <li>Download the JSON file</li>
                      <li>Paste the entire JSON content below</li>
                    </ol>
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
                    <div className="bg-muted p-4 rounded-md">
                      <p className="text-sm font-mono mb-2">Add to Replit Secrets:</p>
                      <div className="space-y-2">
                        <div className="flex items-center gap-2">
                          <code className="text-xs flex-1 bg-background p-2 rounded break-all">
                            FIREBASE_SERVICE_ACCOUNT_JSON={JSON.stringify(JSON.parse(firebaseJson))}
                          </code>
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            onClick={() => {
                              try {
                                const jsonStr = JSON.stringify(JSON.parse(firebaseJson))
                                copyToClipboard(`FIREBASE_SERVICE_ACCOUNT_JSON=${jsonStr}`, 'firebase-full')
                              } catch (e) {
                                toast.error("Failed to format JSON")
                              }
                            }}
                          >
                            {copied === 'firebase-full' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                          </Button>
                        </div>
                        <p className="text-xs text-muted-foreground">
                          Note: In Replit Secrets, paste the JSON as a single-line string (no line breaks)
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
                      handleStepChange(3)
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

            {/* Step 3: GitHub CI (Optional) */}
            {currentStep === 3 && (
              <div className="space-y-6">
                <Alert>
                  <AlertDescription>
                    GitHub Actions CI/CD is optional but recommended for automated Android builds.
                    You can skip this step and configure it later.
                  </AlertDescription>
                </Alert>

                <div className="space-y-4">
                  <div>
                    <h3 className="font-semibold mb-2">GitHub Actions Setup:</h3>
                    <p className="text-sm text-muted-foreground mb-4">
                      Configure secrets in your GitHub repository for automated Android APK builds.
                    </p>
                    
                    <div className="bg-muted p-4 rounded-md space-y-3">
                      <div>
                        <Label className="text-sm font-semibold">Required GitHub Secrets:</Label>
                        <ul className="list-disc list-inside mt-2 space-y-1 text-sm">
                          <li><code>ANDROID_KEYSTORE_BASE64</code> - Base64-encoded keystore</li>
                          <li><code>KEYSTORE_PASSWORD</code> - Keystore password</li>
                          <li><code>ANDROID_KEY_ALIAS</code> - Key alias (e.g., "nexmdm")</li>
                          <li><code>ANDROID_KEY_ALIAS_PASSWORD</code> - Key password</li>
                          <li><code>BACKEND_URL</code> - Your Replit deployment URL</li>
                          <li><code>ADMIN_KEY</code> - Same as ADMIN_KEY secret above</li>
                        </ul>
                      </div>
                    </div>

                    <div className="space-y-2">
                      <Label>Generate Keystore Command:</Label>
                      <div className="bg-muted p-4 rounded-md">
                        <code className="text-xs block mb-2"># Run this in your terminal:</code>
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
                      </div>
                    </div>

                    <div className="space-y-2">
                      <Label>Encode Keystore to Base64:</Label>
                      <div className="bg-muted p-4 rounded-md space-y-2">
                        <div>
                          <code className="text-xs block mb-2"># Linux/Mac:</code>
                          <code className="text-xs block whitespace-pre-wrap break-all mb-4">
                            base64 -w 0 release.keystore
                          </code>
                        </div>
                        <div>
                          <code className="text-xs block mb-2"># Windows (PowerShell):</code>
                          <code className="text-xs block whitespace-pre-wrap break-all">
                            [Convert]::ToBase64String([IO.File]::ReadAllBytes("release.keystore"))
                          </code>
                        </div>
                        <div className="flex gap-2 mt-2">
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={() => copyToClipboard('base64 -w 0 release.keystore', 'base64-linux')}
                          >
                            {copied === 'base64-linux' ? <Check className="h-4 w-4 mr-2" /> : <Copy className="h-4 w-4 mr-2" />}
                            Copy Linux Command
                          </Button>
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={() => copyToClipboard('[Convert]::ToBase64String([IO.File]::ReadAllBytes("release.keystore"))', 'base64-powershell')}
                          >
                            {copied === 'base64-powershell' ? <Check className="h-4 w-4 mr-2" /> : <Copy className="h-4 w-4 mr-2" />}
                            Copy PowerShell Command
                          </Button>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="flex gap-2">
                  <Button variant="outline" onClick={() => handleStepChange(2)}>
                    <ArrowLeft className="mr-2 h-4 w-4" /> Back
                  </Button>
                  <Button
                    onClick={() => {
                      setShowGitHub(true)
                      handleStepChange(4)
                    }}
                    className="flex-1"
                  >
                    Skip GitHub Setup <ArrowRight className="ml-2 h-4 w-4" />
                  </Button>
                  <Button
                    onClick={() => {
                      setShowGitHub(true)
                      handleStepChange(4)
                    }}
                    variant="default"
                  >
                    Configure GitHub <ArrowRight className="ml-2 h-4 w-4" />
                  </Button>
                </div>
              </div>
            )}

            {/* Step 4: Complete */}
            {currentStep === 4 && (
              <div className="space-y-6">
                <div className="text-center">
                  <CheckCircle2 className="h-16 w-16 text-green-500 mx-auto mb-4" />
                  <h2 className="text-2xl font-bold mb-2">Setup Complete!</h2>
                  <p className="text-muted-foreground mb-6">
                    All required configuration is complete. You can now use NexMDM.
                  </p>
                </div>

                <Alert>
                  <AlertDescription>
                    <strong>Next steps:</strong>
                    <ol className="list-decimal list-inside mt-2 space-y-1 text-sm">
                      <li>Make sure all secrets are added to Replit Secrets tab</li>
                      <li>Restart your Repl if needed</li>
                      <li>Create your admin account via the signup page</li>
                      <li>Start enrolling devices!</li>
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
                      "Verify Configuration"
                    )}
                  </Button>
                  <Button
                    onClick={() => {
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

