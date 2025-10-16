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
    
    const body = await request.text()
    
    const response = await fetch(`${BACKEND_URL}/v1/devices/${id}/ping`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Admin': adminKey,
      },
      body: body || undefined,
    })
    
    const contentType = response.headers.get('content-type')
    const isJson = contentType?.includes('application/json')
    
    if (!response.ok) {
      let error
      if (isJson) {
        error = await response.json()
      } else {
        const text = await response.text()
        error = { detail: text || 'Failed to ping device' }
      }
      
      return NextResponse.json(
        { error: error.detail || error.message || 'Failed to ping device' },
        { status: response.status }
      )
    }
    
    const data = isJson ? await response.json() : { ok: true, message: await response.text() }
    return NextResponse.json(data)
  } catch (error) {
    console.error('Error pinging device:', error)
    return NextResponse.json(
      { error: 'Failed to ping device' },
      { status: 500 }
    )
  }
}
