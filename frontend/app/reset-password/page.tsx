"use client"

import { useState, useEffect, Suspense } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { toast } from "sonner"
import { Moon, Sun, KeyRound, Loader2, CheckCircle } from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { useAuth } from "@/lib/auth"
import { useTheme } from "@/contexts/ThemeContext"

function ResetPasswordContent() {
  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [isValidating, setIsValidating] = useState(true)
  const [isValidToken, setIsValidToken] = useState(false)
  const [tokenData, setTokenData] = useState<{ username?: string; expires_at?: string } | null>(null)
  
  const router = useRouter()
  const searchParams = useSearchParams()
  const token = searchParams.get("token")
  const { login } = useAuth()
  const { isDark, toggleTheme } = useTheme()

  useEffect(() => {
    // Validate token when page loads
    if (token) {
      validateToken(token)
    } else {
      setIsValidating(false)
      toast.error("No reset token provided")
    }
  }, [token])

  const validateToken = async (resetToken: string) => {
    try {
      const response = await fetch(`/api/auth/verify-reset-token?token=${encodeURIComponent(resetToken)}`)
      const data = await response.json()

      if (response.ok && data.ok) {
        setIsValidToken(true)
        setTokenData(data)
      } else {
        setIsValidToken(false)
        toast.error(data.detail || "Invalid or expired reset token")
      }
    } catch (error) {
      console.error("Token validation error:", error)
      toast.error("Failed to validate reset token")
      setIsValidToken(false)
    } finally {
      setIsValidating(false)
    }
  }


  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!password.trim() || !confirmPassword.trim()) {
      toast.error("Please enter and confirm your new password")
      return
    }

    if (password !== confirmPassword) {
      toast.error("Passwords do not match")
      return
    }

    if (password.length < 6) {
      toast.error("Password must be at least 6 characters long")
      return
    }

    setIsLoading(true)

    try {
      const formData = new FormData()
      formData.append("token", token!)
      formData.append("new_password", password)

      const response = await fetch("/api/auth/reset-password", {
        method: "POST",
        body: formData,
      })

      const data = await response.json()

      if (response.ok && data.ok) {
        toast.success("Password reset successfully!")
        
        // Auto-login with the new credentials
        if (data.access_token) {
          // Store the token and redirect
          localStorage.setItem('auth_token', data.access_token)
          toast.success("Logging you in...")
          setTimeout(() => {
            router.push('/')
          }, 1000)
        } else {
          // Redirect to login page
          router.push('/login')
        }
      } else {
        toast.error(data.detail || "Failed to reset password")
      }
    } catch (error) {
      console.error("Password reset error:", error)
      toast.error("An error occurred. Please try again.")
    } finally {
      setIsLoading(false)
    }
  }

  if (isValidating) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="flex flex-col items-center space-y-4">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          <p className="text-muted-foreground">Validating reset token...</p>
        </div>
      </div>
    )
  }

  if (!isValidToken) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="w-full max-w-md px-6">
          <Card className="backdrop-blur-xl bg-card/80 border-destructive/50">
            <CardHeader>
              <CardTitle className="text-destructive">Invalid or Expired Token</CardTitle>
              <CardDescription>
                This password reset link is invalid or has expired.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground mb-4">
                Password reset links are valid for 1 hour. Please request a new reset link.
              </p>
              <Button 
                onClick={() => router.push('/login')}
                className="w-full"
              >
                Back to Login
              </Button>
            </CardContent>
          </Card>
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
            <CardTitle>Reset Your Password</CardTitle>
            <CardDescription>
              {tokenData?.username && (
                <span>Enter a new password for <strong>{tokenData.username}</strong></span>
              )}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleResetPassword} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="password">New Password</Label>
                <Input
                  id="password"
                  type="password"
                  placeholder="Enter new password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={isLoading}
                  autoComplete="new-password"
                  autoFocus
                />
                <p className="text-xs text-muted-foreground">
                  Minimum 6 characters
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="confirm-password">Confirm New Password</Label>
                <Input
                  id="confirm-password"
                  type="password"
                  placeholder="Confirm new password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  disabled={isLoading}
                  autoComplete="new-password"
                />
              </div>

              <Button 
                type="submit" 
                className="w-full gap-2" 
                disabled={isLoading || !password || !confirmPassword}
              >
                {isLoading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Resetting Password...
                  </>
                ) : (
                  <>
                    <KeyRound className="h-4 w-4" />
                    Reset Password
                  </>
                )}
              </Button>
            </form>
          </CardContent>
        </Card>

        <div className="mt-6 text-center">
          <Button
            variant="ghost"
            onClick={() => router.push('/login')}
            className="text-sm text-muted-foreground hover:text-primary"
          >
            ← Back to Login
          </Button>
        </div>
      </div>
    </div>
  )
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="flex flex-col items-center space-y-4">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          <p className="text-muted-foreground">Loading...</p>
        </div>
      </div>
    }>
      <ResetPasswordContent />
    </Suspense>
  )
}