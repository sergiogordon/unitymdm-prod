import { NextRequest, NextResponse } from 'next/server'
import { getBackendUrl } from '@/lib/backend-url'

// Configure route for large file downloads
export const maxDuration = 300 // 5 minutes (max for Vercel Pro, adjust for your platform)
export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

const BACKEND_URL = getBackendUrl('/v1/apk/download')

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const startTime = Date.now()
  let apkId: string | undefined
  
  try {
    apkId = (await params).id
    console.log(`[APK DOWNLOAD] Starting download for APK ID: ${apkId}`)
    
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
    
    // Add timeout for large file downloads (5 minutes)
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 300000) // 5 minutes
    
    const backendUrl = `${BACKEND_URL}/v1/apk/download/${apkId}`
    console.log(`[APK DOWNLOAD] Fetching from backend: ${backendUrl}`)
    
    let response: Response
    try {
      response = await fetch(backendUrl, {
        headers: backendHeaders,
        signal: controller.signal,
      })
      clearTimeout(timeoutId)
      console.log(`[APK DOWNLOAD] Backend response status: ${response.status}, has body: ${response.body !== null}`)
    } catch (fetchError) {
      clearTimeout(timeoutId)
      if (fetchError instanceof Error && fetchError.name === 'AbortError') {
        console.error('APK download timeout after 5 minutes')
        return NextResponse.json(
          { error: 'Download timeout - file too large or server too slow' },
          { status: 504 }
        )
      }
      throw fetchError
    }
    
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
    
    // Check if response body exists
    if (!response.body) {
      console.error('APK download: Response body is null')
      return NextResponse.json(
        { error: 'Server returned empty response' },
        { status: 500 }
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
    
    // Ensure Content-Length is preserved (critical for Android download progress)
    const contentLength = response.headers.get('Content-Length')
    if (contentLength) {
      headers.set('Content-Length', contentLength)
    }
    
    // Stream the response body directly
    // Next.js should handle ReadableStream from fetch responses correctly
    try {
      console.log(`[APK DOWNLOAD] Creating NextResponse with stream, Content-Length: ${contentLength || 'unknown'}`)
      
      // Pass the response body stream directly to NextResponse
      // This preserves streaming for large files without buffering
      const streamResponse = new NextResponse(response.body, {
        status: response.status,
        headers,
      })
      
      const duration = Date.now() - startTime
      console.log(`[APK DOWNLOAD] Successfully created stream response in ${duration}ms`)
      
      return streamResponse
    } catch (streamError) {
      console.error('Error creating NextResponse with stream:', streamError)
      const errorDetails = streamError instanceof Error ? {
        message: streamError.message,
        name: streamError.name,
        stack: streamError.stack?.substring(0, 500) // Limit stack trace length
      } : { error: 'Unknown stream error' }
      
      console.error('Stream error details:', JSON.stringify(errorDetails, null, 2))
      
      return NextResponse.json(
        { 
          error: 'Failed to stream APK file', 
          details: errorDetails.message || 'Unknown error',
          error_type: errorDetails.name || 'Unknown'
        },
        { status: 500 }
      )
    }
  } catch (error) {
    const duration = Date.now() - startTime
    console.error(`[APK DOWNLOAD] Error after ${duration}ms for APK ${apkId}:`, error)
    
    const errorMessage = error instanceof Error ? error.message : 'Unknown error'
    const errorName = error instanceof Error ? error.name : 'Unknown'
    const errorStack = error instanceof Error ? error.stack : undefined
    
    // Log full error details for debugging
    console.error(`[APK DOWNLOAD] Error details:`, {
      message: errorMessage,
      name: errorName,
      stack: errorStack?.substring(0, 1000), // First 1000 chars of stack
      apkId,
      backendUrl: BACKEND_URL
    })
    
    return NextResponse.json(
      { 
        error: 'Failed to download APK', 
        details: errorMessage, 
        error_type: errorName,
        apk_id: apkId
      },
      { status: 500 }
    )
  }
}
