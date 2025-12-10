import { NextRequest, NextResponse } from 'next/server'
import { getBackendUrl } from '@/lib/backend-url'

export async function GET(request: NextRequest) {
  try {
    // Resolve backend URL dynamically on each request
    const API_URL = getBackendUrl('/api/auth/verify-reset-token')
    
    const searchParams = request.nextUrl.searchParams
    const token = searchParams.get('token')
    
    if (!token) {
      return NextResponse.json(
        { error: 'Token is required' },
        { status: 400 }
      )
    }
    
    const response = await fetch(`${API_URL}/api/auth/verify-reset-token?token=${encodeURIComponent(token)}`, {
      method: 'GET',
    })

    const data = await response.json()
    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    console.error('Verify reset token proxy error:', error)
    return NextResponse.json(
      { error: 'Failed to verify reset token' },
      { status: 500 }
    )
  }
}