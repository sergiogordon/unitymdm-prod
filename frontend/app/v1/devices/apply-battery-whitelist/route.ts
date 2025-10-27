import { NextRequest, NextResponse } from "next/server"

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000"

export async function POST(request: NextRequest) {
  try {
    const authHeader = request.headers.get('Authorization')
    const body = await request.json()
    
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    }
    
    if (authHeader) {
      headers['Authorization'] = authHeader
    }
    
    const response = await fetch(`${BACKEND_URL}/v1/devices/apply-battery-whitelist`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
    })
    
    if (!response.ok) {
      const error = await response.text()
      console.error('[API-ROUTE] Backend error:', error)
      return NextResponse.json(
        { error: error || 'Failed to apply battery whitelist' },
        { status: response.status }
      )
    }
    
    const data = await response.json()
    return NextResponse.json(data)
  } catch (error) {
    console.error('[API-ROUTE] Exception:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}
