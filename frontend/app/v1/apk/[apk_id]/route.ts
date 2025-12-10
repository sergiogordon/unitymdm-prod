import { NextRequest, NextResponse } from 'next/server'

import { getBackendUrl } from '@/lib/backend-url'

export async function DELETE(
  request: NextRequest,
  context: { params: Promise<{ apk_id: string }> }
) {
  try {
    // Resolve backend URL dynamically on each request
    const API_URL = getBackendUrl('/v1/apk')
    
    const { apk_id } = await context.params
    
    const authHeader = request.headers.get('Authorization')
    const headers: HeadersInit = {}
    if (authHeader) {
      headers['Authorization'] = authHeader
    }

    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 10000)

    const response = await fetch(`${API_URL}/v1/apk/${apk_id}`, {
      method: 'DELETE',
      headers,
      signal: controller.signal,
    })

    clearTimeout(timeoutId)

    const data = await response.json()
    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    console.error('APK delete error:', error)
    return NextResponse.json({ error: 'Failed to delete APK' }, { status: 500 })
  }
}
