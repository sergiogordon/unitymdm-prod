/**
 * React Hook for Device Management
 * Provides real-time device data with WebSocket updates
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { Device } from '@/lib/mock-data'
import { fetchDevices, createDeviceWebSocket } from '@/lib/api-client'

export function useDevices(shouldFetch: boolean = true) {
  const [devices, setDevices] = useState<Device[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [wsConnected, setWsConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  // Fetch devices initially
  const loadDevices = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const fetchedDevices = await fetchDevices()
      setDevices(fetchedDevices)
      setError(null) // Clear any previous errors on success
    } catch (err) {
      console.error('Error loading devices:', err)
      const errorMessage = err instanceof Error ? err.message : 'Failed to load devices'
      setError(errorMessage)
      // Don't clear devices on error - keep showing last known state
    } finally {
      setLoading(false)
    }
  }, [])

  // Handle WebSocket device updates
  const handleDeviceUpdate = useCallback((updatedDevice: Device) => {
    setDevices(prev => {
      const index = prev.findIndex(d => d.id === updatedDevice.id)
      if (index >= 0) {
        // Update existing device
        const newDevices = [...prev]
        newDevices[index] = updatedDevice
        return newDevices
      } else {
        // Add new device
        return [...prev, updatedDevice]
      }
    })
  }, [])

  // Set up WebSocket connection - only if shouldFetch is true
  useEffect(() => {
    if (!shouldFetch) {
      setLoading(false)
      return
    }

    // Initial load
    loadDevices()

    // Connect WebSocket for real-time updates
    const ws = createDeviceWebSocket(
      handleDeviceUpdate,
      () => setWsConnected(true),
      () => setWsConnected(false)
    )
    wsRef.current = ws

    // Cleanup on unmount
    return () => {
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shouldFetch]) // Re-run when shouldFetch changes

  // Refresh devices manually
  const refresh = useCallback(() => {
    loadDevices()
  }, [loadDevices])

  return {
    devices,
    loading,
    error,
    refresh,
    wsConnected
  }
}
