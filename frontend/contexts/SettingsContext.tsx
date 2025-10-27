"use client"

import { createContext, useContext, useState, ReactNode } from "react"

interface SettingsContextType {
  isSettingsOpen: boolean
  openSettings: () => void
  closeSettings: () => void
}

const SettingsContext = createContext<SettingsContextType | undefined>(undefined)

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)

  const openSettings = () => setIsSettingsOpen(true)
  const closeSettings = () => setIsSettingsOpen(false)

  return (
    <SettingsContext.Provider value={{ isSettingsOpen, openSettings, closeSettings }}>
      {children}
    </SettingsContext.Provider>
  )
}

export function useSettings() {
  const context = useContext(SettingsContext)
  if (context === undefined) {
    throw new Error("useSettings must be used within a SettingsProvider")
  }
  return context
}
