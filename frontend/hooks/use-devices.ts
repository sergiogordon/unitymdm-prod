/**
 * React Hook for Device Management
 * Provides real-time device data with WebSocket updates
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { Device } from '@/lib/mock-data'
import { fetchDevices, createDeviceWebSocket } from '@/lib/api-client'

export function useDevices() {
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
    } catch (err) {
      console.error('Error loading devices:', err)
      setError(err instanceof Error ? err.message : 'Failed to load devices')
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

  // Set up WebSocket connection
  useEffect(() => {
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
  }, [loadDevices, handleDeviceUpdate])

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
