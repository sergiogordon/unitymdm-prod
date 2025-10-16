import { NextRequest, NextResponse } from "next/server"

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000"

export async function POST(request: NextRequest) {
  try {
    const authHeader = request.headers.get('Authorization')
    const body = await request.json()
    
    console.log('[API-ROUTE] Received battery whitelist request')
    console.log('[API-ROUTE] Body:', JSON.stringify(body))
    
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    }
    
    if (authHeader) {
      headers['Authorization'] = authHeader
    }
    
    console.log('[API-ROUTE] Sending to backend:', `${BACKEND_URL}/v1/devices/apply-battery-whitelist`)
    
    const response = await fetch(`${BACKEND_URL}/v1/devices/apply-battery-whitelist`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
    })
    
    console.log('[API-ROUTE] Backend response status:', response.status)
    
    if (!response.ok) {
      const error = await response.text()
      console.error('[API-ROUTE] Backend error:', error)
      return NextResponse.json(
        { error: error || 'Failed to apply battery whitelist' },
        { status: response.status }
      )
    }
    
    const data = await response.json()
    console.log('[API-ROUTE] Success response:', data)
    return NextResponse.json(data)
  } catch (error) {
    console.error('[API-ROUTE] Exception:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}
