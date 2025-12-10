import { NextRequest, NextResponse } from 'next/server'

const API_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'

export async function POST(request: NextRequest) {
  try {
    const adminKey = request.headers.get('x-admin-key')
    
    if (!adminKey) {
      return NextResponse.json({ error: 'Admin key required' }, { status: 403 })
    }

    const formData = await request.formData()

    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 30000)

    const response = await fetch(`${API_URL}/v1/apk/upload-init`, {
      method: 'POST',
      headers: {
        'X-Admin-Key': adminKey,
      },
      body: formData,
      signal: controller.signal,
    })

    clearTimeout(timeoutId)

    const data = await response.json()
    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    console.error('APK upload init error:', error)
    return NextResponse.json({ error: 'Failed to initialize upload' }, { status: 500 })
  }
}
