import { NextRequest, NextResponse } from 'next/server'

const BACKEND_URL = 'http://localhost:8000'

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id: apkId } = await params
    
    // Get device token from headers (case-insensitive)
    const deviceToken = request.headers.get('x-device-token') || request.headers.get('X-Device-Token')
    
    console.log(`[APK DOWNLOAD PROXY] APK ID: ${apkId}, Has token: ${!!deviceToken}`)
    
    if (!deviceToken) {
      console.log('[APK DOWNLOAD PROXY] No device token found in headers')
      return NextResponse.json(
        { error: 'Device token required' },
        { status: 401 }
      )
    }
    
    console.log(`[APK DOWNLOAD PROXY] Forwarding to backend with token (first 10): ${deviceToken.substring(0, 10)}...`)
    
    const response = await fetch(`${BACKEND_URL}/v1/apk/download/${apkId}`, {
      headers: {
        'X-Device-Token': deviceToken,
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
