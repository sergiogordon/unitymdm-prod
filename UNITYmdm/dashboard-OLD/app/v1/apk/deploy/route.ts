import { NextRequest, NextResponse } from 'next/server'
import { isDemoRequest, handleDemoRequest } from '@/lib/apiDemoHelper'

const API_URL = 'http://localhost:8000'

export async function POST(request: NextRequest) {
  try {
    // Check if this is a demo mode request
    if (isDemoRequest(request)) {
      return handleDemoRequest(request, '/v1/apk/deploy', 'POST')
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

    const body = await request.json()

    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 60000)

    const response = await fetch(`${API_URL}/v1/apk/deploy`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      signal: controller.signal,
    })

    clearTimeout(timeoutId)

    const data = await response.json()
    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    console.error('APK deploy error:', error)
    return NextResponse.json({ error: 'Failed to deploy APK' }, { status: 500 })
  }
}
