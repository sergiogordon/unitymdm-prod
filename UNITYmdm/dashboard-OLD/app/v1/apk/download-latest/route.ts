import { NextRequest, NextResponse } from 'next/server'

const BACKEND_URL = 'http://localhost:8000'

export async function GET(request: NextRequest) {
  try {
    // Get admin key from headers (case-insensitive)
    const adminKey = request.headers.get('x-admin-key') || request.headers.get('X-Admin-Key')
    
    console.log(`[APK LATEST DOWNLOAD PROXY] Has admin key: ${!!adminKey}`)
    
    if (!adminKey) {
      console.log('[APK LATEST DOWNLOAD PROXY] No admin key found in headers')
      return NextResponse.json(
        { error: 'Admin key required' },
        { status: 401 }
      )
    }
    
    console.log(`[APK LATEST DOWNLOAD PROXY] Forwarding to backend with admin key (first 10): ${adminKey.substring(0, 10)}...`)
    
    const response = await fetch(`${BACKEND_URL}/v1/apk/download-latest`, {
      headers: {
        'X-Admin-Key': adminKey,
      },
    })
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Download failed' }))
      console.log(`[APK LATEST DOWNLOAD PROXY] Backend error: ${response.status}`)
      return NextResponse.json(
        { error: error.detail || 'Failed to download APK' },
        { status: response.status }
      )
    }
    
    // Stream the APK file with proper headers
    const blob = await response.blob()
    const headers = new Headers()
    headers.set('Content-Type', 'application/vnd.android.package-archive')
    headers.set('Content-Disposition', response.headers.get('Content-Disposition') || 'attachment')
    
    // CRITICAL: Forward Content-Length for download progress and validation
    const contentLength = response.headers.get('Content-Length')
    if (contentLength) {
      headers.set('Content-Length', contentLength)
      console.log(`[APK LATEST DOWNLOAD PROXY] Forwarding Content-Length: ${contentLength}`)
    } else {
      // Fallback: Set Content-Length from blob size
      headers.set('Content-Length', blob.size.toString())
      console.log(`[APK LATEST DOWNLOAD PROXY] Setting Content-Length from blob: ${blob.size}`)
    }
    
    console.log(`[APK LATEST DOWNLOAD PROXY] Successfully streaming APK (${blob.size} bytes)`)
    
    return new NextResponse(blob, {
      status: 200,
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
