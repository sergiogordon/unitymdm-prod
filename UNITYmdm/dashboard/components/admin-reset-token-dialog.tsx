"use client"

import { useState } from "react"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { toast } from "sonner"
import { Loader2, Copy, ExternalLink } from "lucide-react"

interface AdminResetTokenDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  adminKey: string
}

export function AdminResetTokenDialog({ open, onOpenChange, adminKey }: AdminResetTokenDialogProps) {
  const [username, setUsername] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [resetData, setResetData] = useState<{
    token: string
    reset_url: string
    expires_at: string
    username: string
  } | null>(null)

  const handleGenerateToken = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!username.trim()) {
      toast.error("Please enter a username")
      return
    }

    setIsLoading(true)

    try {
      const formData = new FormData()
      formData.append("username", username)

      const response = await fetch("/api/auth/admin/generate-reset-token", {
        method: "POST",
        headers: {
          "X-Admin": adminKey,
        },
        body: formData,
      })

      const data = await response.json()

      if (response.ok && data.ok) {
        setResetData(data)
        toast.success(`Reset token generated for ${data.username}`)
      } else {
        toast.error(data.detail || "Failed to generate reset token")
      }
    } catch (error) {
      console.error("Token generation error:", error)
      toast.error("An error occurred. Please try again.")
    } finally {
      setIsLoading(false)
    }
  }

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text)
    toast.success(`${label} copied to clipboard`)
  }

  const handleClose = () => {
    setUsername("")
    setResetData(null)
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>Generate Password Reset Token</DialogTitle>
          <DialogDescription>
            Generate a password reset token for a user who cannot access their email.
          </DialogDescription>
        </DialogHeader>
        
        {!resetData ? (
          <form onSubmit={handleGenerateToken} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                type="text"
                placeholder="Enter username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                disabled={isLoading}
                autoFocus
              />
            </div>
            <div className="flex justify-end space-x-2">
              <Button
                type="button"
                variant="outline"
                onClick={handleClose}
                disabled={isLoading}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={isLoading}>
                {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Generate Token
              </Button>
            </div>
          </form>
        ) : (
          <div className="space-y-4">
            <div className="rounded-lg bg-muted p-4 space-y-3">
              <div>
                <p className="text-sm font-medium text-muted-foreground mb-1">Username</p>
                <p className="font-mono text-sm">{resetData.username}</p>
              </div>
              
              <div>
                <p className="text-sm font-medium text-muted-foreground mb-1">Reset Token</p>
                <div className="flex items-center gap-2">
                  <code className="flex-1 text-xs bg-background p-2 rounded border break-all">
                    {resetData.token}
                  </code>
                  <Button
                    size="icon"
                    variant="ghost"
                    onClick={() => copyToClipboard(resetData.token, "Token")}
                  >
                    <Copy className="h-4 w-4" />
                  </Button>
                </div>
              </div>
              
              <div>
                <p className="text-sm font-medium text-muted-foreground mb-1">Reset URL</p>
                <div className="flex items-center gap-2">
                  <code className="flex-1 text-xs bg-background p-2 rounded border break-all">
                    {resetData.reset_url}
                  </code>
                  <Button
                    size="icon"
                    variant="ghost"
                    onClick={() => copyToClipboard(resetData.reset_url, "URL")}
                  >
                    <Copy className="h-4 w-4" />
                  </Button>
                  <Button
                    size="icon"
                    variant="ghost"
                    onClick={() => window.open(resetData.reset_url, '_blank')}
                  >
                    <ExternalLink className="h-4 w-4" />
                  </Button>
                </div>
              </div>
              
              <div>
                <p className="text-sm font-medium text-muted-foreground mb-1">Expires At</p>
                <p className="text-sm">{new Date(resetData.expires_at).toLocaleString()}</p>
                <p className="text-xs text-muted-foreground mt-1">Valid for 2 hours</p>
              </div>
            </div>
            
            <div className="bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-900 rounded-lg p-3">
              <p className="text-sm text-amber-800 dark:text-amber-200">
                <strong>Security Notice:</strong> Share this token securely with the user. 
                The token can only be used once and expires in 2 hours.
              </p>
            </div>
            
            <div className="flex justify-between">
              <Button
                variant="outline"
                onClick={() => {
                  setResetData(null)
                  setUsername("")
                }}
              >
                Generate Another
              </Button>
              <Button onClick={handleClose}>
                Done
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}