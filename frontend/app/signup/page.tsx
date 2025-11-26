"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { Moon, Sun, UserPlus } from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { signup, isAuthenticated } from "@/lib/api-client"
import { useTheme } from "@/contexts/ThemeContext"
import Link from "next/link"

export default function SignupPage() {
  const [username, setUsername] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const router = useRouter()
  const { isDark, toggleTheme } = useTheme()

  // SetupCheck wrapper handles setup verification
  // It allows signup page to proceed even when backend is temporarily unavailable
  useEffect(() => {
    if (isAuthenticated() && typeof window !== 'undefined' && window.location.pathname === '/signup') {
      router.push('/')
    }
  }, [router])

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!username.trim() || !password.trim()) {
      toast.error("Username and password are required")
      return
    }

    if (username.length < 3) {
      toast.error("Username must be at least 3 characters")
      return
    }

    if (password.length < 6) {
      toast.error("Password must be at least 6 characters")
      return
    }

    if (password !== confirmPassword) {
      toast.error("Passwords do not match")
      return
    }

    if (email && (!email.includes('@') || email.length < 3)) {
      toast.error("Please enter a valid email address")
      return
    }

    setIsLoading(true)

    try {
      const result = await signup(username, password, email || undefined)
      
      if (result.success) {
        toast.success('Account created successfully!')
        router.push('/')
      } else {
        // Show different error messages based on error type
        const errorMessage = result.error || 'Signup failed'
        
        if (result.errorType === 'network') {
          // Network errors - show detailed message with troubleshooting
          toast.error(errorMessage, {
            duration: 8000, // Longer duration for important messages
            description: 'Please check that the backend server is running.'
          })
        } else if (result.errorType === 'validation') {
          // Validation errors - show concise message
          toast.error(errorMessage)
        } else {
          // Server errors or unknown
          toast.error(errorMessage, {
            duration: 5000
          })
        }
      }
    } catch (error: any) {
      // Handle unexpected errors
      const errorMessage = error.message || 'An unexpected error occurred'
      toast.error(errorMessage, {
        duration: 5000,
        description: 'Please try again or contact support if the problem persists.'
      })
      console.error('Signup error:', error)
    } finally {
      setIsLoading(false)
    }
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
            <CardTitle>Create Account</CardTitle>
            <CardDescription>
              Sign up to start managing your mobile devices
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSignup} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="username">Username *</Label>
                <Input
                  id="username"
                  type="text"
                  placeholder="Choose a username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  disabled={isLoading}
                  autoComplete="username"
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="email">
                  Email Address
                  <span className="text-muted-foreground text-xs ml-2">(optional, for password reset)</span>
                </Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="your.email@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={isLoading}
                  autoComplete="email"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="password">Password *</Label>
                <Input
                  id="password"
                  type="password"
                  placeholder="Create a password (min 6 characters)"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={isLoading}
                  autoComplete="new-password"
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="confirmPassword">Confirm Password *</Label>
                <Input
                  id="confirmPassword"
                  type="password"
                  placeholder="Confirm your password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  disabled={isLoading}
                  autoComplete="new-password"
                  required
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
                    Creating account...
                  </>
                ) : (
                  <>
                    <UserPlus className="h-4 w-4" />
                    Create Account
                  </>
                )}
              </Button>
            </form>
          </CardContent>
        </Card>

        <p className="mt-6 text-center text-sm text-muted-foreground">
          Already have an account?{' '}
          <Link href="/login" className="text-primary hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  )
}
