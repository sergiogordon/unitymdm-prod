import { NextRequest, NextResponse } from 'next/server'
import { isDemoRequest, handleDemoRequest } from '@/lib/apiDemoHelper'

const BACKEND_URL = 'http://localhost:8000'

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    
    // Check if this is a demo mode request
    if (isDemoRequest(request)) {
      return handleDemoRequest(request, `/v1/devices/${id}/events`, 'GET')
    }

    const authHeader = request.headers.get('authorization')
    const { searchParams } = new URL(request.url)
    const limit = searchParams.get('limit') || '5'
    
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    }
    
    if (authHeader) {
      headers['Authorization'] = authHeader
    }
    
    const response = await fetch(`${BACKEND_URL}/v1/devices/${id}/events?limit=${limit}`, {
      headers,
    })
    
    if (!response.ok) {
      throw new Error(`Backend returned ${response.status}`)
    }
    
    const data = await response.json()
    return NextResponse.json(data)
  } catch (error) {
    console.error('Error proxying device events to backend:', error)
    return NextResponse.json({ error: 'Failed to fetch device events' }, { status: 500 })
  }
}
