import { NextRequest, NextResponse } from 'next/server'
import { getBackendUrl } from '@/lib/backend-url'

const BACKEND_URL = getBackendUrl('/v1/apk/download')

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id: apkId } = await params
    
    // Get device token or authorization bearer token
    const deviceToken = request.headers.get('x-device-token') || request.headers.get('X-Device-Token')
    const authHeader = request.headers.get('authorization') || request.headers.get('Authorization')
    
    if (!deviceToken && !authHeader) {
      return NextResponse.json(
        { error: 'Authentication required (device token or enrollment token)' },
        { status: 401 }
      )
    }
    
    // Prepare headers for backend request
    const backendHeaders: Record<string, string> = {}
    
    if (deviceToken) {
      backendHeaders['X-Device-Token'] = deviceToken
    } else if (authHeader) {
      backendHeaders['Authorization'] = authHeader
    }
    
    // Forward conditional headers for cache validation
    const ifNoneMatch = request.headers.get('If-None-Match')
    if (ifNoneMatch) {
      backendHeaders['If-None-Match'] = ifNoneMatch
    }
    
    const ifModifiedSince = request.headers.get('If-Modified-Since')
    if (ifModifiedSince) {
      backendHeaders['If-Modified-Since'] = ifModifiedSince
    }
    
    const response = await fetch(`${BACKEND_URL}/v1/apk/download/${apkId}`, {
      headers: backendHeaders,
    })
    
    if (!response.ok) {
      // Handle 304 Not Modified
      if (response.status === 304) {
        const headers = new Headers()
        response.headers.forEach((value, key) => {
          if (key.toLowerCase() === 'etag' || key.toLowerCase() === 'last-modified' || key.toLowerCase() === 'cache-control') {
            headers.set(key, value)
          }
        })
        return new NextResponse(null, {
          status: 304,
          headers,
        })
      }
      
      const error = await response.json().catch(() => ({ detail: 'Download failed' }))
      return NextResponse.json(
        { error: error.detail || 'Failed to download APK' },
        { status: response.status }
      )
    }
    
    // Stream the response body instead of buffering
    const headers = new Headers()
    
    // Forward all relevant headers from backend
    response.headers.forEach((value, key) => {
      const lowerKey = key.toLowerCase()
      // Forward cache headers, content headers, but skip transfer-encoding
      if (lowerKey !== 'transfer-encoding' && lowerKey !== 'connection') {
        headers.set(key, value)
      }
    })
    
    // Ensure Content-Type is set
    if (!headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/vnd.android.package-archive')
    }
    
    // Ensure Content-Disposition is set
    if (!headers.has('Content-Disposition')) {
      headers.set('Content-Disposition', 'attachment')
    }
    
    // Stream the response body
    return new NextResponse(response.body, {
      status: response.status,
      headers,
    })
  } catch (error) {
    console.error('Error downloading APK:', error)
    return NextResponse.json(
      { error: 'Failed to download APK' },
      { status: 500 }
    )
  }
}
