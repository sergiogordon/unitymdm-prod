import { NextRequest, NextResponse } from 'next/server'
import { getBackendUrl } from '@/lib/backend-url'

export async function POST(request: NextRequest) {
  try {
    // Resolve backend URL dynamically on each request
    const backendUrl = getBackendUrl('/api/auth/logout')
    
    const sessionToken = request.cookies.get('session_token')?.value
    const response = await fetch(`${backendUrl}/api/auth/logout`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Cookie': sessionToken ? `session_token=${sessionToken}` : '',
      },
    })

    const data = await response.json()

    const nextResponse = NextResponse.json(data)
    nextResponse.cookies.delete('session_token')

    return nextResponse
  } catch (error) {
    console.error('Logout error:', error)
    return NextResponse.json(
      { detail: 'Internal server error' },
      { status: 500 }
    )
  }
}
