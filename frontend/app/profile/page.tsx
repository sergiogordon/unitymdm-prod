"use client"

import { useState, useEffect } from "react"
import { toast } from "sonner"
import { Mail, User, Calendar, Save } from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { PageHeader } from "@/components/page-header"
import { PageWrapper } from "@/components/page-wrapper"
import { getCurrentUser, updateUserEmail } from "@/lib/api-client"

export default function ProfilePage() {
  const [user, setUser] = useState<{ id: number; username: string; email: string | null; created_at: string } | null>(null)
  const [newEmail, setNewEmail] = useState("")
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)

  useEffect(() => {
    loadUser()
  }, [])

  const loadUser = async () => {
    try {
      const userData = await getCurrentUser()
      if (userData) {
        setUser(userData)
        setNewEmail(userData.email || "")
      }
    } catch (error) {
      console.error('Failed to load user:', error)
      toast.error('Failed to load profile')
    } finally {
      setIsLoading(false)
    }
  }

  const handleUpdateEmail = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!newEmail.trim()) {
      toast.error("Email address is required")
      return
    }

    if (!newEmail.includes('@') || newEmail.length < 3) {
      toast.error("Please enter a valid email address")
      return
    }

    setIsSaving(true)

    try {
      const result = await updateUserEmail(newEmail)
      
      if (result.success) {
        toast.success('Email updated successfully!')
        await loadUser()
      } else {
        toast.error(result.error || 'Failed to update email')
      }
    } catch (error: any) {
      toast.error(error.message || 'Failed to update email')
      console.error('Update email error:', error)
    } finally {
      setIsSaving(false)
    }
  }

  if (isLoading) {
    return (
      <PageWrapper>
        <div className="flex items-center justify-center h-64">
          <span className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
        </div>
      </PageWrapper>
    )
  }

  if (!user) {
    return (
      <PageWrapper>
        <div className="text-center py-12">
          <p className="text-muted-foreground">Failed to load profile</p>
        </div>
      </PageWrapper>
    )
  }

  const formattedDate = new Date(user.created_at).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  })

  return (
    <PageWrapper>
      <PageHeader 
        title="Profile Settings"
        description="Manage your account information and preferences"
      />

      <div className="grid gap-6 max-w-2xl">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <User className="h-5 w-5" />
              Account Information
            </CardTitle>
            <CardDescription>
              Your basic account details
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <Label className="text-muted-foreground">Username</Label>
              <p className="text-lg font-medium mt-1">{user.username}</p>
            </div>

            <div>
              <Label className="text-muted-foreground flex items-center gap-2">
                <Calendar className="h-4 w-4" />
                Member Since
              </Label>
              <p className="text-lg font-medium mt-1">{formattedDate}</p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Mail className="h-5 w-5" />
              Email Address
            </CardTitle>
            <CardDescription>
              Used for password reset and important notifications
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleUpdateEmail} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="email">Email Address</Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="your.email@example.com"
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                  disabled={isSaving}
                  autoComplete="email"
                />
                {!user.email && (
                  <p className="text-sm text-muted-foreground">
                    No email address set. Add one to enable password reset.
                  </p>
                )}
              </div>

              <Button 
                type="submit" 
                className="gap-2" 
                disabled={isSaving || newEmail === user.email}
              >
                {isSaving ? (
                  <>
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                    Saving...
                  </>
                ) : (
                  <>
                    <Save className="h-4 w-4" />
                    Save Email
                  </>
                )}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </PageWrapper>
  )
}
