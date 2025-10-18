import { NextRequest, NextResponse } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'

export async function POST(request: NextRequest) {
  try {
    const sessionToken = request.cookies.get('session_token')?.value

    const body = await request.json()

    const response = await fetch(`${BACKEND_URL}/v1/devices/bulk-delete`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Cookie': sessionToken ? `session_token=${sessionToken}` : '',
      },
      body: JSON.stringify(body),
    })

    const data = await response.json()

    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || 'Failed to delete devices' },
        { status: response.status }
      )
    }

    return NextResponse.json(data)
  } catch (error) {
    return NextResponse.json(
      { error: 'Failed to delete devices' },
      { status: 500 }
    )
  }
}
