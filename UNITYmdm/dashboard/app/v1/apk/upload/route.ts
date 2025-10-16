import { NextRequest, NextResponse } from 'next/server'
import { cookies } from 'next/headers'

const API_URL = 'http://localhost:8000'

export async function POST(request: NextRequest) {
  try {
    const cookieStore = await cookies()
    const sessionCookie = cookieStore.get('session_token')

    const formData = await request.formData()

    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 60000)

    const response = await fetch(`${API_URL}/v1/apk/upload`, {
      method: 'POST',
      headers: {
        'Cookie': sessionCookie ? `session_token=${sessionCookie.value}` : '',
      },
      body: formData,
      signal: controller.signal,
    })

    clearTimeout(timeoutId)

    const data = await response.json()
    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    console.error('APK upload error:', error)
    return NextResponse.json({ error: 'Failed to upload APK' }, { status: 500 })
  }
}
