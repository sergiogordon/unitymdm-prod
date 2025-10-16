"use client"

import { useEffect } from 'react'
import { AuthProvider } from '@/lib/auth'
import { isDemoMode } from '@/lib/demoUtils'
import { DemoApiService } from '@/lib/demoApiService'

export function Providers({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    if (typeof window === 'undefined') return

    const originalFetch = window.fetch
    
    // Override fetch when in demo mode
    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      if (isDemoMode()) {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url
        return DemoApiService.fetch(url, init)
      }
      return originalFetch(input, init)
    }

    return () => {
      window.fetch = originalFetch
    }
  }, [])

  return <AuthProvider>{children}</AuthProvider>
}
