import { NextRequest, NextResponse } from 'next/server'
import { isDemoRequest, handleDemoRequest } from '@/lib/apiDemoHelper'

const BACKEND_URL = 'http://localhost:8000'

export async function GET(request: NextRequest) {
  try {
    // Check if this is a demo mode request
    if (isDemoRequest(request)) {
      return handleDemoRequest(request, '/v1/metrics', 'GET')
    }

    // Get JWT token from Authorization header
    const authHeader = request.headers.get('Authorization')
    
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    }
    
    // Forward Authorization header if present
    if (authHeader) {
      headers['Authorization'] = authHeader
    }
    
    const response = await fetch(`${BACKEND_URL}/v1/metrics`, {
      headers
    })
    
    if (!response.ok) {
      throw new Error(`Backend returned ${response.status}`)
    }
    
    const data = await response.json()
    return NextResponse.json(data)
  } catch (error) {
    console.error('Error proxying metrics to backend:', error)
    return NextResponse.json({ error: 'Failed to fetch metrics' }, { status: 500 })
  }
}
