import { NextRequest, NextResponse } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'

export async function GET(request: NextRequest) {
  try {
    // Get admin key from headers (case-insensitive)
    const adminKey = request.headers.get('x-admin-key') || request.headers.get('X-Admin-Key')
    
    if (!adminKey) {
      return NextResponse.json(
        { error: 'Admin key required' },
        { status: 401 }
      )
    }
    
    // Forward conditional headers for cache validation
    const backendHeaders: Record<string, string> = {
      'X-Admin-Key': adminKey,
    }
    
    const ifNoneMatch = request.headers.get('If-None-Match')
    if (ifNoneMatch) {
      backendHeaders['If-None-Match'] = ifNoneMatch
    }
    
    const ifModifiedSince = request.headers.get('If-Modified-Since')
    if (ifModifiedSince) {
      backendHeaders['If-Modified-Since'] = ifModifiedSince
    }
    
    const response = await fetch(`${BACKEND_URL}/v1/apk/download-latest`, {
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
    
    // Stream the response body
    return new NextResponse(response.body, {
      status: response.status,
      headers,
    })
  } catch (error) {
    console.error('[APK LATEST DOWNLOAD PROXY] Error:', error)
    return NextResponse.json(
      { error: 'Failed to download APK' },
      { status: 500 }
    )
  }
}
