import { NextRequest, NextResponse } from 'next/server'
import { getBackendUrl } from '@/lib/backend-url'

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ build_id: string }> }
) {
  try {
    // Resolve backend URL dynamically on each request
    const API_URL = getBackendUrl('/admin/apk/download')
    
    const { build_id } = await params

    const adminKey = process.env.ADMIN_KEY
    if (!adminKey) {
      return NextResponse.json(
        { error: 'Admin key not configured' },
        { status: 500 }
      )
    }

    const response = await fetch(`${API_URL}/admin/apk/download/${build_id}`, {
      headers: {
        'X-Admin': adminKey,
      },
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Download failed' }))
      return NextResponse.json(error, { status: response.status })
    }

    const blob = await response.blob()
    const headers = new Headers()
    headers.set('Content-Type', 'application/vnd.android.package-archive')
    headers.set(
      'Content-Disposition',
      response.headers.get('Content-Disposition') || 'attachment'
    )

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
    console.error('APK download error:', error)
    return NextResponse.json(
      { error: 'Failed to download APK' },
      { status: 500 }
    )
  }
}
