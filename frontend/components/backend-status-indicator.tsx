"use client"

import { useState, useEffect, useCallback } from "react"

interface HealthStatus {
  status: "healthy" | "unhealthy" | "checking"
  uptime?: number
  lastCheck?: Date
  error?: string
}

const CHECK_INTERVAL = 10000 // Check every 10 seconds
const TIMEOUT = 5000 // 5 second timeout

export function BackendStatusIndicator() {
  const [health, setHealth] = useState<HealthStatus>({ status: "checking" })

  const checkHealth = useCallback(async () => {
    try {
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), TIMEOUT)

      const response = await fetch("/api/proxy/healthz", {
        signal: controller.signal,
        cache: "no-store",
      })

      clearTimeout(timeoutId)

      if (response.ok) {
        const data = await response.json()
        setHealth({
          status: "healthy",
          uptime: data.uptime_seconds,
          lastCheck: new Date(),
        })
      } else {
        setHealth({
          status: "unhealthy",
          lastCheck: new Date(),
          error: `HTTP ${response.status}`,
        })
      }
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        setHealth({
          status: "unhealthy",
          lastCheck: new Date(),
          error: "Timeout",
        })
      } else {
        setHealth({
          status: "unhealthy",
          lastCheck: new Date(),
          error: "Connection failed",
        })
      }
    }
  }, [])

  useEffect(() => {
    // Initial check
    checkHealth()

    // Set up interval
    const interval = setInterval(checkHealth, CHECK_INTERVAL)

    return () => clearInterval(interval)
  }, [checkHealth])

  const formatUptime = (seconds?: number) => {
    if (!seconds) return ""
    const days = Math.floor(seconds / 86400)
    const hours = Math.floor((seconds % 86400) / 3600)
    const mins = Math.floor((seconds % 3600) / 60)

    if (days > 0) return `${days}d ${hours}h`
    if (hours > 0) return `${hours}h ${mins}m`
    return `${mins}m`
  }

  const getStatusColor = () => {
    switch (health.status) {
      case "healthy":
        return "bg-green-500"
      case "unhealthy":
        return "bg-red-500"
      case "checking":
        return "bg-yellow-500"
    }
  }

  const getStatusText = () => {
    switch (health.status) {
      case "healthy":
        return "Backend Online"
      case "unhealthy":
        return "Backend Offline"
      case "checking":
        return "Checking..."
    }
  }

  const getBorderColor = () => {
    switch (health.status) {
      case "healthy":
        return "border-green-500/30"
      case "unhealthy":
        return "border-red-500/30"
      case "checking":
        return "border-yellow-500/30"
    }
  }

  const getBgColor = () => {
    switch (health.status) {
      case "healthy":
        return "bg-green-500/10"
      case "unhealthy":
        return "bg-red-500/10"
      case "checking":
        return "bg-yellow-500/10"
    }
  }

  const getTextColor = () => {
    switch (health.status) {
      case "healthy":
        return "text-green-600 dark:text-green-400"
      case "unhealthy":
        return "text-red-600 dark:text-red-400"
      case "checking":
        return "text-yellow-600 dark:text-yellow-400"
    }
  }

  return (
    <div
      className={`fixed bottom-6 right-6 z-50 ${getBgColor()} ${getBorderColor()} border rounded-lg px-3 py-2 shadow-lg backdrop-blur-sm transition-all duration-300 hover:scale-105`}
      title={
        health.status === "healthy" && health.uptime
          ? `Uptime: ${formatUptime(health.uptime)}`
          : health.error
          ? `Error: ${health.error}`
          : "Backend status"
      }
    >
      <div className="flex items-center gap-2">
        <div className="relative">
          <div
            className={`w-2.5 h-2.5 rounded-full ${getStatusColor()} ${
              health.status === "healthy" ? "animate-pulse" : ""
            }`}
          />
          {health.status === "checking" && (
            <div
              className={`absolute inset-0 w-2.5 h-2.5 rounded-full ${getStatusColor()} animate-ping opacity-75`}
            />
          )}
        </div>
        <div className="flex flex-col">
          <span className={`text-xs font-medium ${getTextColor()}`}>
            {getStatusText()}
          </span>
          {health.status === "healthy" && health.uptime && (
            <span className="text-[10px] text-gray-500 dark:text-gray-400">
              {formatUptime(health.uptime)}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

