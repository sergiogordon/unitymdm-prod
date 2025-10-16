"use client"

import { useState } from "react"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { toast } from "sonner"
import { Loader2 } from "lucide-react"

interface ForgotPasswordModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function ForgotPasswordModal({ open, onOpenChange }: ForgotPasswordModalProps) {
  const [usernameOrEmail, setUsernameOrEmail] = useState("")
  const [isLoading, setIsLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!usernameOrEmail.trim()) {
      toast.error("Please enter your username or email")
      return
    }

    setIsLoading(true)

    try {
      const formData = new FormData()
      formData.append("username_or_email", usernameOrEmail)

      const response = await fetch("/api/auth/forgot-password", {
        method: "POST",
        body: formData,
      })

      const data = await response.json()

      if (response.ok) {
        toast.success(data.message || "Password reset instructions sent!")
        setUsernameOrEmail("")
        onOpenChange(false)
      } else {
        if (response.status === 429) {
          toast.error("Too many requests. Please try again later.")
        } else {
          toast.error(data.detail || "Failed to request password reset")
        }
      }
    } catch (error) {
      console.error("Password reset request error:", error)
      toast.error("An error occurred. Please try again.")
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>Reset Password</DialogTitle>
          <DialogDescription>
            Enter your username or email address and we'll send you a password reset link.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="username-email">Username or Email</Label>
            <Input
              id="username-email"
              type="text"
              placeholder="Enter your username or email"
              value={usernameOrEmail}
              onChange={(e) => setUsernameOrEmail(e.target.value)}
              disabled={isLoading}
              autoFocus
            />
          </div>
          <div className="flex justify-end space-x-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isLoading}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isLoading}>
              {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Send Reset Link
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}