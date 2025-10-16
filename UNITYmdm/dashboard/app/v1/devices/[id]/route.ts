import { NextRequest, NextResponse } from 'next/server'

const BACKEND_URL = 'http://localhost:8000'

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    const sessionToken = request.cookies.get('session_token')?.value
    const adminKey = process.env.ADMIN_KEY
    
    if (!adminKey) {
      return NextResponse.json(
        { error: 'Admin key not configured' },
        { status: 500 }
      )
    }
    
    const response = await fetch(`${BACKEND_URL}/v1/devices/${id}`, {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
        'x-admin': adminKey,
        'Cookie': sessionToken ? `session_token=${sessionToken}` : '',
      },
    })
    
    if (!response.ok) {
      const error = await response.json()
      return NextResponse.json(
        { error: error.detail || 'Failed to delete device' },
        { status: response.status }
      )
    }
    
    const data = await response.json()
    return NextResponse.json(data)
  } catch (error) {
    console.error('Error deleting device:', error)
    return NextResponse.json(
      { error: 'Failed to delete device' },
      { status: 500 }
    )
  }
}
