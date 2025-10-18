import { NextRequest, NextResponse } from 'next/server'

const BACKEND_URL = 'http://localhost:8000'

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    const adminKey = process.env.ADMIN_KEY
    
    if (!adminKey) {
      return NextResponse.json(
        { error: 'Admin key not configured' },
        { status: 500 }
      )
    }
    
    const body = await request.json().catch(() => ({}))
    const duration = body.duration || 30
    
    const response = await fetch(`${BACKEND_URL}/v1/devices/${id}/ring?duration_seconds=${duration}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Admin': adminKey,
      },
    })
    
    const contentType = response.headers.get('content-type')
    const isJson = contentType?.includes('application/json')
    
    if (!response.ok) {
      let error
      if (isJson) {
        error = await response.json()
      } else {
        const text = await response.text()
        error = { detail: text || 'Failed to ring device' }
      }
      
      return NextResponse.json(
        { error: error.detail || error.message || 'Failed to ring device' },
        { status: response.status }
      )
    }
    
    const data = isJson ? await response.json() : { ok: true, message: await response.text() }
    return NextResponse.json(data)
  } catch (error) {
    console.error('Error ringing device:', error)
    return NextResponse.json(
      { error: 'Failed to ring device' },
      { status: 500 }
    )
  }
}
