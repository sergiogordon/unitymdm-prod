import { NextRequest, NextResponse } from 'next/server'

export async function GET(request: NextRequest) {
  try {
    // Get JWT token from Authorization header
    const authHeader = request.headers.get('Authorization')
    
    // Check for demo token
    if (authHeader?.includes('demo_token')) {
      return NextResponse.json({
        id: 1,
        username: 'demo',
        created_at: new Date().toISOString()
      })
    }
    
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    }
    
    // Forward Authorization header if present
    if (authHeader) {
      headers['Authorization'] = authHeader
    }
    
    const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000'
    const response = await fetch(`${backendUrl}/api/auth/user`, {
      method: 'GET',
      headers
    })

    const data = await response.json()

    if (!response.ok) {
      return NextResponse.json(data, { status: response.status })
    }

    return NextResponse.json(data)
  } catch (error) {
    console.error('Get user error:', error)
    return NextResponse.json(
      { detail: 'Internal server error' },
      { status: 500 }
    )
  }
}
