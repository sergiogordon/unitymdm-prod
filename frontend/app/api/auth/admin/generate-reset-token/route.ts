import { NextRequest, NextResponse } from 'next/server'
import { getBackendUrl } from '@/lib/backend-url'

export async function POST(request: NextRequest) {
  try {
    // Resolve backend URL dynamically on each request
    const API_URL = getBackendUrl('/api/auth/admin/generate-reset-token')
    
    const formData = await request.formData()
    const adminKey = request.headers.get('X-Admin')
    
    if (!adminKey) {
      return NextResponse.json(
        { error: 'Admin key is required' },
        { status: 401 }
      )
    }
    
    const response = await fetch(`${API_URL}/api/auth/admin/generate-reset-token`, {
      method: 'POST',
      headers: {
        'X-Admin': adminKey,
      },
      body: formData,
    })

    const data = await response.json()
    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    console.error('Admin generate reset token proxy error:', error)
    return NextResponse.json(
      { error: 'Failed to generate reset token' },
      { status: 500 }
    )
  }
}