import { NextRequest, NextResponse } from 'next/server'
import { cookies } from 'next/headers'

import { getBackendUrl } from '@/lib/backend-url'

const BACKEND_URL = getBackendUrl('/v1/apk/download-web')

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id: apkId } = await params
    
    // Get ALL cookies for proper session authentication
    const cookieStore = await cookies()
    const sessionToken = cookieStore.get('session_token')?.value
    
    if (!sessionToken) {
      return NextResponse.json(
        { error: 'Authentication required' },
        { status: 401 }
      )
    }
    
    // Build complete cookie string with all session-related cookies
    const cookieHeader = cookieStore.getAll()
      .map(cookie => `${cookie.name}=${cookie.value}`)
      .join('; ')
    
    // Call backend download-web endpoint with all cookies for proper auth
    const response = await fetch(`${BACKEND_URL}/v1/apk/download-web/${apkId}`, {
      headers: {
        'Cookie': cookieHeader,
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
    
    const contentLength = response.headers.get('Content-Length')
    if (contentLength) {
      headers.set('Content-Length', contentLength)
    } else {
      headers.set('Content-Length', blob.size.toString())
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
