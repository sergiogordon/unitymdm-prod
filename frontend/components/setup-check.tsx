"use client"

import { useEffect, useState } from "react"
import { useRouter, usePathname } from "next/navigation"
import { Loader2 } from "lucide-react"

const BACKEND_URL = '/api/proxy'
const SETUP_CHECK_TIMEOUT_MS = 10000 // 10 second timeout, then proceed anyway

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

    let timeoutId: NodeJS.Timeout | null = null
    let aborted = false

    // Fallback timeout: if check takes too long, proceed anyway
    // This prevents infinite loading when backend is overloaded
    timeoutId = setTimeout(() => {
      if (!aborted) {
        console.warn('Setup check timed out after 10s, proceeding anyway')
        // Assume setup is complete if we're timing out
        // (likely means backend is just slow, not that setup is incomplete)
        sessionStorage.setItem('setup_checked', 'ready')
        setChecking(false)
        aborted = true
      }
    }, SETUP_CHECK_TIMEOUT_MS)

    const checkSetup = async () => {
      try {
        const response = await fetch(`${BACKEND_URL}/api/setup/status`)
        
        if (aborted) return // Timeout already fired
        
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
        
        // If response not OK, check if setup was previously verified
        // This includes 400, 401, 404, 500, 502, 503, etc.
        const previouslyVerified = sessionStorage.getItem('setup_checked') === 'ready'
        
        if (previouslyVerified) {
          // Setup was previously verified - allow access even if backend is temporarily unavailable
          // This handles cases where backend goes down after setup was completed
          setChecking(false)
          return
        }
        
        // Setup not verified or backend unavailable - redirect to setup
        sessionStorage.removeItem('setup_checked')
        setSetupRequired(true)
        router.push('/setup')
        return
      } catch (error) {
        if (aborted) return // Timeout already fired
        
        // Network error or backend unreachable
        console.error('Setup check failed:', error)
        
        // Check if setup was previously verified before allowing access
        const previouslyVerified = sessionStorage.getItem('setup_checked') === 'ready'
        
        if (previouslyVerified) {
          // Setup was previously verified - allow access even if backend is temporarily unavailable
          // This handles cases where backend goes down after setup was completed
          setChecking(false)
          return
        }
        
        // Setup not verified or backend unavailable - redirect to setup
        sessionStorage.removeItem('setup_checked')
        setSetupRequired(true)
        router.push('/setup')
      } finally {
        if (timeoutId) clearTimeout(timeoutId)
      }
    }

    checkSetup()

    return () => {
      if (timeoutId) clearTimeout(timeoutId)
      aborted = true
    }
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

