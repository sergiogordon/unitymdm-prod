import { NextRequest, NextResponse } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url)
    const alias = searchParams.get('alias')
    
    if (!alias) {
      return NextResponse.json({ detail: 'Alias is required' }, { status: 400 })
    }
    
    const response = await fetch(`${BACKEND_URL}/v1/enrollment-qr-payload?alias=${encodeURIComponent(alias)}`, {
      headers: {
        'Content-Type': 'application/json',
      },
    })
    
    if (!response.ok) {
      const error = await response.json()
      return NextResponse.json(error, { status: response.status })
    }
    
    const data = await response.json()
    return NextResponse.json(data)
  } catch (error) {
    console.error('Error proxying to backend:', error)
    return NextResponse.json({ detail: 'Failed to generate QR payload' }, { status: 500 })
  }
}
