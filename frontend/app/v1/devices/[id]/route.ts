import { NextRequest, NextResponse } from 'next/server'
import { handleBackendError, handleProxyError } from '@/lib/api-error-handler'

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
      return handleBackendError(response, 'Failed to delete device')
    }
    
    const data = await response.json()
    return NextResponse.json(data)
  } catch (error) {
    return handleProxyError(error, 'Failed to delete device')
  }
}
