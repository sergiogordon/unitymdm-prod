"use client"

import { ReactNode, useState, useEffect } from "react"
import { X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useRouter } from "next/navigation"
import { enableDemoMode } from "@/lib/demoApiService"

export default function DemoLayout({ children }: { children: ReactNode }) {
  const [isDark, setIsDark] = useState(false)
  const router = useRouter()

  useEffect(() => {
    enableDemoMode()
    const isDarkMode = localStorage.getItem('darkMode') === 'true'
    setIsDark(isDarkMode)
    if (isDarkMode) {
      document.documentElement.classList.add("dark")
    } else {
      document.documentElement.classList.remove("dark")
    }
  }, [])

  const handleExitDemo = () => {
    localStorage.removeItem('demo_mode')
    localStorage.removeItem('access_token')
    localStorage.removeItem('user')
    router.push('/login')
  }

  return (
    <>
      <div className="fixed top-0 z-50 w-full bg-gradient-to-r from-blue-500 to-purple-500 px-4 py-2">
        <div className="flex items-center justify-center gap-3 text-white">
          <span className="text-sm font-medium">
            🎯 Demo Mode - Explore with sample data
          </span>
          <Button 
            size="sm" 
            variant="ghost" 
            onClick={handleExitDemo}
            className="h-7 gap-1.5 bg-white/20 text-white hover:bg-white/30"
          >
            <X className="h-3 w-3" />
            Exit Demo
          </Button>
        </div>
      </div>
      <div className="pt-10">
        {children}
      </div>
    </>
  )
}
