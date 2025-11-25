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
import { Checkbox } from "@/components/ui/checkbox"
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { ChevronDown, ExternalLink, HelpCircle } from "lucide-react"

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
      id: 'github',
      title: 'GitHub CI/CD (Recommended)',
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

            {/* Step 3: GitHub CI (Recommended) */}
            {currentStep === 3 && (
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
                  <Button variant="outline" onClick={() => handleStepChange(2)}>
                    <ArrowLeft className="mr-2 h-4 w-4" /> Back
                  </Button>
                  {skipGitHubCI ? (
                    <Button
                      onClick={() => {
                        setShowGitHub(true)
                        handleStepChange(4)
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
                        handleStepChange(4)
                      }}
                      className="flex-1"
                    >
                      Continue to Next Step <ArrowRight className="ml-2 h-4 w-4" />
                    </Button>
                  )}
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

