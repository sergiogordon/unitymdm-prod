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

    // Skip check if already checked in this session
    const setupChecked = sessionStorage.getItem('setup_checked')
    if (setupChecked === 'true') {
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
            sessionStorage.setItem('setup_checked', 'true')
            setSetupRequired(true)
            router.push('/setup')
            return
          }
        }
        
        // Setup is complete or check failed (assume OK to avoid redirect loops)
        sessionStorage.setItem('setup_checked', 'true')
        setChecking(false)
      } catch (error) {
        // If backend is down, don't redirect (let user proceed)
        // They'll see errors on pages that need backend
        console.error('Setup check failed:', error)
        sessionStorage.setItem('setup_checked', 'true')
        setChecking(false)
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

