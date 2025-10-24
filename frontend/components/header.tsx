"use client"

import { Moon, Sun } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { useTheme } from "@/contexts/ThemeContext"

interface HeaderProps {
  className?: string
}

export function Header({
  className,
}: HeaderProps) {
  const { isDark, toggleTheme } = useTheme()
  
  return (
    <header
      className={cn("fixed top-0 z-50 w-full border-b border-border/40 bg-background/80 backdrop-blur-xl", className)}
    >
      <div className="mx-auto flex h-[60px] max-w-[1280px] items-center justify-end px-6 md:px-8">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={toggleTheme} className="h-9 w-9" aria-label="Toggle theme">
            {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
        </div>
      </div>
    </header>
  )
}
