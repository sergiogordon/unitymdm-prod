import { NextRequest, NextResponse } from 'next/server'
import { getBackendUrl } from '@/lib/backend-url'

export async function POST(request: NextRequest) {
  try {
    // Resolve backend URL dynamically on each request
    const backendUrl = getBackendUrl('/api/auth/login')
    
    const body = await request.json()
    const response = await fetch(`${backendUrl}/api/auth/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    })

    const data = await response.json()

    if (!response.ok) {
      return NextResponse.json(data, { status: response.status })
    }

    // Set session cookie on frontend port (5000) using session_id from backend
    const nextResponse = NextResponse.json(data)
    
    if (data.session_id) {
      console.log('[LOGIN] Setting session cookie with ID:', data.session_id)
      nextResponse.cookies.set('session_token', data.session_id, {
        httpOnly: false,  // Allow JS access for WebSocket auth
        maxAge: 60 * 60 * 24 * 7,  // 7 days
        sameSite: 'lax',
        path: '/',
      })
      console.log('[LOGIN] Cookie set successfully')
    } else {
      console.error('[LOGIN] No session_id in response!')
    }

    return nextResponse
  } catch (error) {
    console.error('Login error:', error)
    return NextResponse.json(
      { detail: 'Internal server error' },
      { status: 500 }
    )
  }
}
