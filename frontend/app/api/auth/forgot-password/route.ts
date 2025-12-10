import { NextRequest, NextResponse } from 'next/server'
import { getBackendUrl } from '@/lib/backend-url'

export async function POST(request: NextRequest) {
  try {
    // Resolve backend URL dynamically on each request
    const API_URL = getBackendUrl('/api/auth/forgot-password')
    
    const formData = await request.formData()
    
    const response = await fetch(`${API_URL}/api/auth/forgot-password`, {
      method: 'POST',
      body: formData,
    })

    const data = await response.json()
    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    console.error('Forgot password proxy error:', error)
    return NextResponse.json(
      { error: 'Failed to process password reset request' },
      { status: 500 }
    )
  }
}