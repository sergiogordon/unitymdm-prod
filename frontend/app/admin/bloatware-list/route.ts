import { NextRequest, NextResponse } from 'next/server'
import { getBackendUrl } from '@/lib/backend-url'

export async function GET(request: NextRequest) {
  try {
    // Resolve backend URL dynamically on each request
    const BACKEND_URL = getBackendUrl('/admin/bloatware-list')
    
    const adminKey = request.headers.get('x-admin-key') || request.headers.get('X-Admin-Key')
    
    if (!adminKey) {
      return NextResponse.json(
        { error: 'Admin key required' },
        { status: 401 }
      )
    }
    
    const response = await fetch(`${BACKEND_URL}/admin/bloatware-list`, {
      headers: {
        'X-Admin-Key': adminKey,
      },
    })
    
    if (!response.ok) {
      return new NextResponse('Failed to fetch bloatware list', {
        status: response.status,
      })
    }
    
    const text = await response.text()
    return new NextResponse(text, {
      status: 200,
      headers: {
        'Content-Type': 'text/plain',
      },
    })
  } catch (error) {
    console.error('[BLOATWARE PROXY] Error:', error)
    return new NextResponse('Failed to fetch bloatware list', {
      status: 500,
    })
  }
}
