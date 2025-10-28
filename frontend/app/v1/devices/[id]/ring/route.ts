import { NextRequest, NextResponse } from 'next/server'
import { handleBackendError, handleProxyError } from '@/lib/api-error-handler'

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
    
    if (!response.ok) {
      return handleBackendError(response, 'Failed to ring device')
    }
    
    const contentType = response.headers.get('content-type')
    const isJson = contentType?.includes('application/json')
    const data = isJson ? await response.json() : { ok: true, message: await response.text() }
    return NextResponse.json(data)
  } catch (error) {
    return handleProxyError(error, 'Failed to ring device')
  }
}
