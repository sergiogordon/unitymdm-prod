import { NextRequest, NextResponse } from 'next/server'

const BACKEND_URL = 'http://localhost:8000'

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
    
    const response = await fetch(`${BACKEND_URL}/v1/apk/download-latest`, {
      headers: {
        'X-Admin-Key': adminKey,
      },
    })
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Download failed' }))
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
    } else {
      // Fallback: Set Content-Length from blob size
      headers.set('Content-Length', blob.size.toString())
    }
    
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
