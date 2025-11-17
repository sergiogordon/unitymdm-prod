"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { Moon, Sun, LogIn, Loader2 } from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { useAuth } from "@/lib/auth"
import { ForgotPasswordModal } from "@/components/forgot-password-modal"
import { useTheme } from "@/contexts/ThemeContext"

const BACKEND_URL = '/api/proxy'

export default function LoginPage() {
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [showForgotPassword, setShowForgotPassword] = useState(false)
  const [checkingSetup, setCheckingSetup] = useState(true)
  const router = useRouter()
  const { login, isAuthenticated } = useAuth()
  const { isDark, toggleTheme } = useTheme()

  // Check setup status before allowing login
  useEffect(() => {
    const checkSetup = async () => {
      try {
        const response = await fetch(`${BACKEND_URL}/api/setup/status`)
        if (response.ok) {
          const status = await response.json()
          if (!status.ready) {
            // Setup not complete, redirect to setup wizard
            router.push('/setup')
            return
          }
        }
        // Setup is complete or check failed - allow login page to render
        setCheckingSetup(false)
      } catch (error) {
        // If backend is unreachable, assume setup needed
        console.error('Setup check failed:', error)
        router.push('/setup')
      }
    }

    checkSetup()
  }, [router])

  // Only redirect if we're actually on the login page and user is authenticated
  useEffect(() => {
    if (!checkingSetup && isAuthenticated && typeof window !== 'undefined' && window.location.pathname === '/login') {
      router.push('/')
    }
  }, [isAuthenticated, router, checkingSetup])

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!username.trim() || !password.trim()) {
      toast.error("Please enter both username and password")
      return
    }

    setIsLoading(true)

    try {
      await login(username, password)
      toast.success('Login successful!')
    } catch (error: any) {
      toast.error(error.message || 'Login failed')
      console.error('Login error:', error)
    } finally {
      setIsLoading(false)
    }
  }

  if (checkingSetup) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center">
          <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4" />
          <p className="text-muted-foreground">Checking configuration...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="absolute top-6 right-6">
        <Button variant="ghost" size="icon" onClick={toggleTheme} className="h-9 w-9">
          {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </Button>
      </div>

      <div className="w-full max-w-md px-6">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold tracking-tight mb-2">UNITYmdm</h1>
          <p className="text-muted-foreground">Mobile Device Management</p>
        </div>

        <Card className="backdrop-blur-xl bg-card/80 border-border/40">
          <CardHeader>
            <CardTitle>Sign In</CardTitle>
            <CardDescription>
              Enter your credentials to access the dashboard
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleLogin} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="username">Username</Label>
                <Input
                  id="username"
                  type="text"
                  placeholder="Enter your username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  disabled={isLoading}
                  autoComplete="username"
                />
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label htmlFor="password">Password</Label>
                  <button
                    type="button"
                    onClick={() => setShowForgotPassword(true)}
                    className="text-sm text-muted-foreground hover:text-primary transition-colors"
                  >
                    Forgot password?
                  </button>
                </div>
                <Input
                  id="password"
                  type="password"
                  placeholder="Enter your password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={isLoading}
                  autoComplete="current-password"
                />
              </div>

              <Button 
                type="submit" 
                className="w-full gap-2" 
                disabled={isLoading}
              >
                {isLoading ? (
                  <>
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                    Signing in...
                  </>
                ) : (
                  <>
                    <LogIn className="h-4 w-4" />
                    Sign In
                  </>
                )}
              </Button>
            </form>
          </CardContent>
        </Card>

        <p className="mt-6 text-center text-sm text-muted-foreground">
          Don't have an account?{' '}
          <a href="/signup" className="text-primary hover:underline">
            Sign up
          </a>
        </p>
      </div>

      <ForgotPasswordModal
        open={showForgotPassword}
        onOpenChange={setShowForgotPassword}
      />
    </div>
  )
}
