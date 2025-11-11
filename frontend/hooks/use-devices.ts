/**
 * React Hook for Device Management
 * Provides real-time device data with WebSocket updates and pagination
 * Includes client-side caching and request debouncing for performance
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { Device } from '@/lib/mock-data'
import { fetchDevices, createDeviceWebSocket } from '@/lib/api-client'

interface Pagination {
  page: number
  limit: number
  total_count: number
  total_pages: number
  has_next: boolean
  has_prev: boolean
}

// Client-side cache with TTL (5 seconds)
const deviceCache = new Map<string, { data: { devices: Device[], pagination: Pagination }, timestamp: number }>()
const CACHE_TTL = 5000 // 5 seconds

function getCacheKey(page: number, limit: number): string {
  return `devices:${page}:${limit}`
}

function getCachedData(page: number, limit: number): { devices: Device[], pagination: Pagination } | null {
  const key = getCacheKey(page, limit)
  const cached = deviceCache.get(key)
  if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
    return cached.data
  }
  if (cached) {
    deviceCache.delete(key) // Remove expired entry
  }
  return null
}

function setCachedData(page: number, limit: number, data: { devices: Device[], pagination: Pagination }) {
  const key = getCacheKey(page, limit)
  deviceCache.set(key, { data, timestamp: Date.now() })
}

function invalidateCache() {
  deviceCache.clear()
}

export function useDevices(shouldFetch: boolean = true, initialPage: number = 1, initialLimit: number = 25) {
  const [devices, setDevices] = useState<Device[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [wsConnected, setWsConnected] = useState(false)
  const [pagination, setPagination] = useState<Pagination | null>(null)
  const [currentPage, setCurrentPage] = useState(initialPage)
  const [pageSize, setPageSize] = useState(initialLimit)
  const wsRef = useRef<WebSocket | null>(null)
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null)

  // Fetch devices with client-side caching and debouncing
  const loadDevices = useCallback(async (page: number = currentPage, limit: number = pageSize, useCache: boolean = true) => {
    // Check cache first
    if (useCache) {
      const cached = getCachedData(page, limit)
      if (cached) {
        setDevices(cached.devices)
        setPagination(cached.pagination)
        setCurrentPage(page)
        setPageSize(limit)
        setLoading(false)
        return
      }
    }
    
    try {
      setLoading(true)
      setError(null)
      const result = await fetchDevices(page, limit)
      setDevices(result.devices)
      setPagination(result.pagination)
      setCurrentPage(page)
      setPageSize(limit)
      setError(null) // Clear any previous errors on success
      
      // Cache the result
      setCachedData(page, limit, result)
    } catch (err) {
      console.error('Error loading devices:', err)
      const errorMessage = err instanceof Error ? err.message : 'Failed to load devices'
      setError(errorMessage)
      // Don't clear devices on error - keep showing last known state
    } finally {
      setLoading(false)
    }
  }, [currentPage, pageSize])

  // Handle WebSocket device updates
  const handleDeviceUpdate = useCallback((updatedDevice: Device) => {
    setDevices(prev => {
      const index = prev.findIndex(d => d.id === updatedDevice.id)
      if (index >= 0) {
        // Update existing device
        const newDevices = [...prev]
        newDevices[index] = updatedDevice
        // Invalidate cache when device is updated
        invalidateCache()
        return newDevices
      } else {
        // Add new device (only if we're on page 1)
        if (currentPage === 1) {
          invalidateCache()
          return [...prev, updatedDevice]
        }
        return prev
      }
    })
  }, [currentPage])

  // Set up WebSocket connection - only if shouldFetch is true
  useEffect(() => {
    if (!shouldFetch) {
      setLoading(false)
      return
    }

    // Initial load
    loadDevices(currentPage, pageSize)

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

  // Re-fetch when page or page size changes (with debouncing for rapid changes)
  useEffect(() => {
    if (!shouldFetch) return
    
    // Clear any pending debounce
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current)
    }
    
    // Debounce rapid page changes (300ms)
    debounceTimerRef.current = setTimeout(() => {
      loadDevices(currentPage, pageSize, true)
    }, 300)
    
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentPage, pageSize])

  // Refresh devices manually (bypass cache)
  const refresh = useCallback(() => {
    invalidateCache()
    loadDevices(currentPage, pageSize, false)
  }, [loadDevices, currentPage, pageSize])

  // Go to next page
  const nextPage = useCallback(() => {
    if (pagination?.has_next) {
      setCurrentPage(prev => prev + 1)
    }
  }, [pagination])

  // Go to previous page
  const prevPage = useCallback(() => {
    if (pagination?.has_prev) {
      setCurrentPage(prev => prev - 1)
    }
  }, [pagination])

  // Change page size
  const changePageSize = useCallback((newSize: number) => {
    setPageSize(newSize)
    setCurrentPage(1) // Reset to page 1 when changing page size
  }, [])

  return {
    devices,
    loading,
    error,
    refresh,
    wsConnected,
    pagination,
    currentPage,
    pageSize,
    nextPage,
    prevPage,
    changePageSize
  }
}
