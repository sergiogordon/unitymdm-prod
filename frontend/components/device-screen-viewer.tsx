"use client"

import { useEffect, useRef, useState } from "react"
import { X, Maximize2, Minimize2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { toast } from "sonner"

interface DeviceScreenViewerProps {
  deviceId: string
  deviceAlias: string
  onClose: () => void
}

export function DeviceScreenViewer({ deviceId, deviceAlias, onClose }: DeviceScreenViewerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [lastFrameTime, setLastFrameTime] = useState<number>(0)
  const [fps, setFps] = useState<number>(0)
  const [latency, setLatency] = useState<number>(0)
  const [reconnectAttempt, setReconnectAttempt] = useState(0)
  const [isReconnecting, setIsReconnecting] = useState(false)
  const [quality, setQuality] = useState<'low' | 'medium' | 'high'>('medium')
  const [autoQuality, setAutoQuality] = useState(true)
  const [showTextInput, setShowTextInput] = useState(false)
  const frameCountRef = useRef(0)
  const lastFpsUpdate = useRef(Date.now())
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const touchStartRef = useRef<{ x: number; y: number; time: number } | null>(null)
  const longPressTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const maxReconnectAttempts = 5

  useEffect(() => {
    connectWebSocket()
    return () => {
      disconnectWebSocket()
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
    }
  }, [deviceId, quality])

  useEffect(() => {
    if (!autoQuality || !isConnected) return
    
    if (latency > 250) {
      if (quality !== 'low') {
        console.log('Auto-adjusting quality to low due to high latency')
        setQuality('low')
      }
    } else if (latency > 150) {
      if (quality !== 'medium') {
        console.log('Auto-adjusting quality to medium')
        setQuality('medium')
      }
    } else if (latency < 100 && latency > 0) {
      if (quality !== 'high') {
        console.log('Auto-adjusting quality to high due to good latency')
        setQuality('high')
      }
    }
  }, [latency, autoQuality, isConnected])

  const connectWebSocket = () => {
    // WebSocket must connect directly to backend (port 8000), not through Next.js
    // Port 8000 is exposed in .replit config for both local and Replit environments
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.hostname
    
    // Get session cookie and pass as query param (cookies don't transfer between ports)
    console.log('[DEBUG] All cookies:', document.cookie)
    const sessionToken = document.cookie
      .split('; ')
      .find(row => row.startsWith('session_token='))
      ?.split('=')[1]
    
    console.log('[DEBUG] Extracted session_token:', sessionToken ? '***found***' : 'NOT FOUND')
    
    if (!sessionToken) {
      console.error('No session cookie found - cannot authenticate WebSocket')
      toast.error('Authentication required. Please refresh the page.')
      return
    }
    
    const wsUrl = `${protocol}//${host}:8000/ws/stream/view/${deviceId}?token=${sessionToken}`
    
    console.log(`Connecting to device screen stream: ${deviceId} at ${wsUrl.replace(/token=[^&]+/, 'token=***')}`)
    
    const ws = new WebSocket(wsUrl)
    ws.binaryType = 'arraybuffer'
    
    ws.onopen = () => {
      console.log('Screen stream connected')
      setIsConnected(true)
      setIsReconnecting(false)
      setReconnectAttempt(0)
      frameCountRef.current = 0
      lastFpsUpdate.current = Date.now()
      toast.success('Screen stream connected')
    }
    
    ws.onmessage = async (event) => {
      if (event.data instanceof ArrayBuffer) {
        const now = Date.now()
        const timeSinceLastFrame = now - lastFrameTime
        setLastFrameTime(now)
        setLatency(timeSinceLastFrame)
        
        frameCountRef.current++
        const elapsed = now - lastFpsUpdate.current
        if (elapsed >= 1000) {
          const currentFps = (frameCountRef.current / elapsed) * 1000
          setFps(Math.round(currentFps))
          frameCountRef.current = 0
          lastFpsUpdate.current = now
        }
        
        const data = new Uint8Array(event.data)
        const headerEnd = findHeaderEnd(data)
        
        if (headerEnd === -1) {
          console.error('Invalid frame: no header found')
          return
        }
        
        const headerStr = new TextDecoder().decode(data.slice(0, headerEnd))
        const [width, height] = headerStr.split(':').map(Number)
        
        if (!width || !height) {
          console.error('Invalid frame dimensions')
          return
        }
        
        const jpegData = data.slice(headerEnd + 1)
        const blob = new Blob([jpegData], { type: 'image/jpeg' })
        const img = new Image()
        
        img.onload = () => {
          const canvas = canvasRef.current
          if (canvas) {
            canvas.width = width
            canvas.height = height
            const ctx = canvas.getContext('2d')
            if (ctx) {
              ctx.drawImage(img, 0, 0, width, height)
            }
          }
          URL.revokeObjectURL(img.src)
        }
        
        img.src = URL.createObjectURL(blob)
      }
    }
    
    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
      toast.error('Stream connection error')
    }
    
    ws.onclose = (event) => {
      console.log('Screen stream disconnected', event.code, event.reason)
      setIsConnected(false)
      
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      
      let errorMessage = 'Connection lost'
      if (event.code === 1008) {
        errorMessage = event.reason || 'Authentication failed'
      } else if (event.code === 1006) {
        errorMessage = 'Network error or device offline'
      }
      
      if (reconnectAttempt >= maxReconnectAttempts) {
        toast.error(`${errorMessage}. Failed after ${maxReconnectAttempts} attempts. Click retry to reconnect.`)
        setIsReconnecting(false)
        return
      }
      
      const backoffDelay = Math.min(1000 * Math.pow(2, reconnectAttempt), 15000)
      setIsReconnecting(true)
      setReconnectAttempt(prev => prev + 1)
      
      reconnectTimeoutRef.current = setTimeout(() => {
        if (wsRef.current === ws) {
          console.log(`Reconnecting... (attempt ${reconnectAttempt + 1}/${maxReconnectAttempts})`)
          connectWebSocket()
        }
      }, backoffDelay)
    }
    
    wsRef.current = ws
  }

  const findHeaderEnd = (data: Uint8Array): number => {
    let colonCount = 0
    for (let i = 0; i < Math.min(data.length, 50); i++) {
      if (data[i] === 58) {
        colonCount++
        if (colonCount === 2) {
          return i
        }
      }
    }
    return -1
  }

  const disconnectWebSocket = () => {
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
  }

  const getCanvasCoordinates = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current
    if (!canvas) return null
    
    const rect = canvas.getBoundingClientRect()
    const scaleX = canvas.width / rect.width
    const scaleY = canvas.height / rect.height
    
    const x = (e.clientX - rect.left) * scaleX
    const y = (e.clientY - rect.top) * scaleY
    
    return { x, y }
  }

  const sendCommand = async (command: string, params: any) => {
    try {
      const token = localStorage.getItem('auth_token')
      const response = await fetch('/v1/remote/command', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          device_ids: [deviceId],
          command,
          params,
        }),
      })
      
      if (!response.ok) {
        toast.error(`Failed to send ${command} command`)
      }
    } catch (error) {
      console.error(`Failed to send ${command} command:`, error)
      toast.error(`Failed to send ${command} command`)
    }
  }

  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const coords = getCanvasCoordinates(e)
    if (!coords) return
    
    touchStartRef.current = { x: coords.x, y: coords.y, time: Date.now() }
    
    longPressTimeoutRef.current = setTimeout(() => {
      console.log('Long press detected')
      sendCommand('long_press', { x: coords.x, y: coords.y })
      touchStartRef.current = null
    }, 500)
  }

  const handleMouseUp = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (longPressTimeoutRef.current) {
      clearTimeout(longPressTimeoutRef.current)
      longPressTimeoutRef.current = null
    }
    
    if (!touchStartRef.current) return
    
    const coords = getCanvasCoordinates(e)
    if (!coords) return
    
    const startPos = touchStartRef.current
    const deltaX = coords.x - startPos.x
    const deltaY = coords.y - startPos.y
    const distance = Math.sqrt(deltaX * deltaX + deltaY * deltaY)
    const duration = Date.now() - startPos.time
    
    if (distance > 50 && duration < 300) {
      console.log(`Swipe detected: dx=${deltaX}, dy=${deltaY}`)
      sendCommand('swipe', { 
        x1: startPos.x, 
        y1: startPos.y, 
        x2: coords.x, 
        y2: coords.y,
        duration: 100
      })
    } else if (distance < 20) {
      console.log(`Tap at (${Math.round(coords.x)}, ${Math.round(coords.y)})`)
      sendCommand('tap', { x: coords.x, y: coords.y })
    }
    
    touchStartRef.current = null
  }

  const handleMouseLeave = () => {
    if (longPressTimeoutRef.current) {
      clearTimeout(longPressTimeoutRef.current)
      longPressTimeoutRef.current = null
    }
    touchStartRef.current = null
  }

  const handleTextInput = async (text: string) => {
    if (!text) return
    await sendCommand('input_text', { text })
    setShowTextInput(false)
  }

  const handlePasteToDevice = async () => {
    try {
      const text = await navigator.clipboard.readText()
      if (!text) {
        toast.error('Clipboard is empty')
        return
      }
      await sendCommand('set_clipboard', { text })
      toast.success('Pasted to device clipboard')
    } catch (error) {
      console.error('Failed to read clipboard:', error)
      toast.error('Failed to read clipboard. Please grant clipboard permission.')
    }
  }

  const handleCopyFromDevice = async () => {
    try {
      const token = localStorage.getItem('auth_token')
      const response = await fetch('/v1/remote/command', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          device_ids: [deviceId],
          command: 'get_clipboard',
          params: {},
        }),
      })
      
      if (!response.ok) {
        toast.error('Failed to get device clipboard')
        return
      }

      const data = await response.json()
      
      // The clipboard content will be sent via WebSocket or polling
      // For now, we'll use a simple approach: wait for the response
      setTimeout(async () => {
        try {
          const clipboardResponse = await fetch(`/v1/devices/${deviceId}/clipboard`)
          if (clipboardResponse.ok) {
            const clipboardData = await clipboardResponse.json()
            if (clipboardData.text) {
              await navigator.clipboard.writeText(clipboardData.text)
              toast.success('Copied to your clipboard')
            }
          }
        } catch (err) {
          console.error('Failed to retrieve clipboard:', err)
        }
      }, 1000)
      
    } catch (error) {
      console.error('Failed to get device clipboard:', error)
      toast.error('Failed to get device clipboard')
    }
  }

  const toggleFullscreen = () => {
    setIsFullscreen(!isFullscreen)
  }

  const manualReconnect = () => {
    setReconnectAttempt(0)
    setIsReconnecting(false)
    disconnectWebSocket()
    connectWebSocket()
  }

  const getLatencyColor = () => {
    if (latency < 100) return 'text-green-500'
    if (latency < 200) return 'text-yellow-500'
    return 'text-red-500'
  }

  const getQualitySettings = () => {
    switch (quality) {
      case 'low': return { width: 360, quality: 50 }
      case 'medium': return { width: 540, quality: 70 }
      case 'high': return { width: 720, quality: 85 }
    }
  }

  return (
    <div className={`
      ${isFullscreen ? 'fixed inset-0 z-50 bg-background' : 'rounded-lg border border-border bg-card'}
      overflow-hidden
    `}>
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex-1">
          <h3 className="font-semibold">{deviceAlias}</h3>
          <div className="flex items-center gap-4 text-xs mt-1">
            <span className={isConnected ? 'text-green-500' : isReconnecting ? 'text-yellow-500' : 'text-red-500'}>
              {isConnected ? '● Connected' : isReconnecting ? `○ Reconnecting (${reconnectAttempt}/${maxReconnectAttempts})` : '○ Disconnected'}
            </span>
            {isConnected && (
              <>
                <span>{fps} FPS</span>
                <span className={getLatencyColor()}>{latency}ms</span>
                <div className="flex items-center gap-1">
                  <label className="flex items-center gap-1 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={autoQuality}
                      onChange={(e) => setAutoQuality(e.target.checked)}
                      className="w-3 h-3"
                    />
                    <span className="text-xs">Auto</span>
                  </label>
                  <select
                    value={quality}
                    onChange={(e) => {
                      setQuality(e.target.value as 'low' | 'medium' | 'high')
                      setAutoQuality(false)
                    }}
                    disabled={autoQuality}
                    className="bg-background border border-border rounded px-1 py-0.5 text-xs disabled:opacity-50"
                  >
                    <option value="low">Low (360p)</option>
                    <option value="medium">Medium (540p)</option>
                    <option value="high">High (720p)</option>
                  </select>
                </div>
              </>
            )}
          </div>
        </div>
        <div className="flex gap-2">
          {!isConnected && !isReconnecting && (
            <Button
              variant="outline"
              size="sm"
              onClick={manualReconnect}
              className="h-8 text-xs"
            >
              Retry
            </Button>
          )}
          <Button
            variant="ghost"
            size="icon"
            onClick={toggleFullscreen}
          >
            {isFullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>
      
      <div className={`
        flex items-center justify-center bg-black/90
        ${isFullscreen ? 'h-[calc(100vh-60px)]' : 'h-[700px]'}
      `}>
        {!isConnected ? (
          <div className="text-center text-muted-foreground">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent mx-auto mb-2" />
            <p>{isReconnecting ? `Reconnecting... (${reconnectAttempt}/${maxReconnectAttempts})` : 'Connecting to device...'}</p>
          </div>
        ) : (
          <canvas
            ref={canvasRef}
            onMouseDown={handleMouseDown}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseLeave}
            className="cursor-crosshair"
            style={{ 
              imageRendering: 'auto',
              aspectRatio: '9/16',
              maxWidth: '450px',
              maxHeight: '100%',
              width: 'auto',
              height: 'auto'
            }}
          />
        )}
      </div>
      
      {isConnected && (
        <div className="border-t border-border px-4 py-2">
          <div className="flex items-center justify-between">
            <div className="text-xs text-muted-foreground">
              Click: tap • Drag: swipe • Hold 0.5s: long press
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handlePasteToDevice}
                className="h-7 text-xs"
              >
                Paste to Device
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleCopyFromDevice}
                className="h-7 text-xs"
              >
                Copy from Device
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowTextInput(true)}
                className="h-7 text-xs"
              >
                Type Text
              </Button>
            </div>
          </div>
        </div>
      )}
      
      {showTextInput && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setShowTextInput(false)}>
          <div className="bg-card border border-border rounded-lg p-4 w-96 max-w-[90vw]" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-semibold mb-3">Send Text to Device</h3>
            <form onSubmit={(e) => {
              e.preventDefault()
              const formData = new FormData(e.currentTarget)
              const text = formData.get('text') as string
              handleTextInput(text)
            }}>
              <input
                type="text"
                name="text"
                placeholder="Enter text to type on device..."
                className="w-full px-3 py-2 bg-background border border-border rounded text-sm mb-3"
                autoFocus
              />
              <div className="flex gap-2 justify-end">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowTextInput(false)}
                >
                  Cancel
                </Button>
                <Button type="submit" size="sm">
                  Send
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
