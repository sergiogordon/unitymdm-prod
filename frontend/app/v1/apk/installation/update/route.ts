import { NextRequest, NextResponse } from 'next/server'

const BACKEND_URL = 'http://localhost:8000'

export async function POST(request: NextRequest) {
  try {
    const url = new URL(request.url)
    const body = await request.json()
    
    // Forward query parameters (installation_id, etc.)
    const queryString = url.searchParams.toString()
    const backendUrl = `${BACKEND_URL}/v1/apk/installation/update${queryString ? `?${queryString}` : ''}`
    
    // Get device token from headers (case-insensitive)
    const deviceToken = request.headers.get('x-device-token') || request.headers.get('X-Device-Token')
    
    const response = await fetch(backendUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(deviceToken ? { 'X-Device-Token': deviceToken } : {}),
      },
      body: JSON.stringify(body),
    })
    
    if (!response.ok) {
      const error = await response.json()
      return NextResponse.json(
        { error: error.detail || 'Failed to update installation status' },
        { status: response.status }
      )
    }
    
    const data = await response.json()
    return NextResponse.json(data)
  } catch (error) {
    console.error('Error updating installation status:', error)
    return NextResponse.json(
      { error: 'Failed to update installation status' },
      { status: 500 }
    )
  }
}
