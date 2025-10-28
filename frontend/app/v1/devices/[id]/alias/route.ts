import { NextRequest, NextResponse } from 'next/server'
import { handleBackendError, handleProxyError } from '@/lib/api-error-handler'

const BACKEND_URL = 'http://localhost:8000'

export async function PATCH(
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
    
    const body = await request.json()
    
    const response = await fetch(`${BACKEND_URL}/v1/devices/${id}/alias`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'x-admin': adminKey,
        'Cookie': sessionToken ? `session_token=${sessionToken}` : '',
      },
      body: JSON.stringify(body),
    })
    
    if (!response.ok) {
      return handleBackendError(response, 'Failed to update alias')
    }
    
    const data = await response.json()
    return NextResponse.json(data)
  } catch (error) {
    return handleProxyError(error, 'Failed to update alias')
  }
}
