import { NextRequest, NextResponse } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'

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
    
    const response = await fetch(`${BACKEND_URL}/v1/apk/download/${apkId}`, {
      headers: backendHeaders,
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
    
    // CRITICAL: Forward Content-Length for Android download progress
    const contentLength = response.headers.get('Content-Length')
    if (contentLength) {
      headers.set('Content-Length', contentLength)
      console.log(`[APK DOWNLOAD PROXY] Forwarding Content-Length: ${contentLength}`)
    } else {
      // Fallback: Set Content-Length from blob size
      headers.set('Content-Length', blob.size.toString())
      console.log(`[APK DOWNLOAD PROXY] Setting Content-Length from blob: ${blob.size}`)
    }
    
    return new NextResponse(blob, {
      status: 200,
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
