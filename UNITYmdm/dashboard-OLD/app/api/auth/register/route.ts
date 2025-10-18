import { NextRequest, NextResponse } from 'next/server'

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    
    const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000'
    const response = await fetch(`${backendUrl}/api/auth/register`, {
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
      nextResponse.cookies.set('session_token', data.session_id, {
        httpOnly: false,  // Allow JS access for WebSocket auth
        maxAge: 60 * 60 * 24 * 7,  // 7 days
        sameSite: 'lax',
        path: '/',
      })
    }

    return nextResponse
  } catch (error) {
    console.error('Register error:', error)
    return NextResponse.json(
      { detail: 'Internal server error' },
      { status: 500 }
    )
  }
}
