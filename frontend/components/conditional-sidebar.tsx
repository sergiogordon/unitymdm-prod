"use client"

import { usePathname } from "next/navigation"
import { Sidebar } from "@/components/sidebar"
import { useAuth } from "@/lib/auth"
import { ReactNode } from "react"

export function ConditionalSidebar({ children }: { children?: ReactNode }) {
  const pathname = usePathname()
  const { isAuthenticated, isLoading } = useAuth()

  // Hide sidebar on login page or when not authenticated
  const shouldShowSidebar = isAuthenticated && pathname !== '/login'

  if (isLoading || !shouldShowSidebar) {
    return <>{children}</>
  }

  return (
    <>
      <Sidebar />
      <div className="pl-64">{children}</div>
    </>
  )
}
