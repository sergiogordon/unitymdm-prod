"use client"

import { useEffect, useState } from "react"
import { useRouter, usePathname } from "next/navigation"
import { Loader2 } from "lucide-react"

const BACKEND_URL = '/api/proxy'

export function SetupCheck({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const [checking, setChecking] = useState(true)
  const [setupRequired, setSetupRequired] = useState(false)

  useEffect(() => {
    // Skip check for setup page itself
    if (pathname === '/setup') {
      setChecking(false)
      return
    }

    // Only skip check if setup is confirmed complete (ready === true)
    // Don't skip if we haven't checked yet or if setup was incomplete
    const setupChecked = sessionStorage.getItem('setup_checked')
    if (setupChecked === 'ready') {
      setChecking(false)
      return
    }

    const checkSetup = async () => {
      try {
        const response = await fetch(`${BACKEND_URL}/api/setup/status`)
        
        if (response.ok) {
          const status = await response.json()
          if (!status.ready) {
            // Setup not complete, redirect to setup wizard
            // Clear any cached check status to allow re-checking
            sessionStorage.removeItem('setup_checked')
            setSetupRequired(true)
            router.push('/setup')
            return
          } else {
            // Setup is complete, cache this result
            sessionStorage.setItem('setup_checked', 'ready')
            setChecking(false)
            return
          }
        }
        
        // If response not OK, assume setup needed - redirect to setup for any error
        // This includes 400, 401, 404, 500, 502, 503, etc.
        sessionStorage.removeItem('setup_checked')
        setSetupRequired(true)
        router.push('/setup')
        return
      } catch (error) {
        // Network error or backend unreachable - assume setup needed
        // Clear cache to allow re-checking
        sessionStorage.removeItem('setup_checked')
        console.error('Setup check failed:', error)
        // Only redirect if we're not already on a public page
        if (pathname !== '/signup') {
          setSetupRequired(true)
          router.push('/setup')
        } else {
          setChecking(false)
        }
      }
    }

    checkSetup()
  }, [pathname, router])

  if (checking) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center">
          <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4" />
          <p className="text-muted-foreground">Checking configuration...</p>
        </div>
      </div>
    )
  }

  if (setupRequired) {
    return null // Will redirect
  }

  return <>{children}</>
}

