import { NextRequest, NextResponse } from 'next/server'

const API_URL = 'http://localhost:8000'

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    const token = request.headers.get('Authorization')
    const body = await request.json()

    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    }
    if (token) {
      headers['Authorization'] = token
    }

    const response = await fetch(`${API_URL}/v1/devices/${id}/settings`, {
      method: 'PATCH',
      headers,
      body: JSON.stringify(body),
    })

    const data = await response.json()
    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    console.error('Device settings update error:', error)
    return NextResponse.json({ error: 'Failed to update device settings' }, { status: 500 })
  }
}
