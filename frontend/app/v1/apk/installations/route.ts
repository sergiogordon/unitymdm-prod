import { NextRequest, NextResponse } from 'next/server'
import { isDemoRequest, handleDemoRequest } from '@/lib/apiDemoHelper'

const API_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'

export async function GET(request: NextRequest) {
  try {
    // Check if this is a demo mode request
    if (isDemoRequest(request)) {
      return handleDemoRequest(request, '/v1/apk/installations', 'GET')
    }

    // Get JWT token from Authorization header
    const authHeader = request.headers.get('Authorization')
    
    const headers: HeadersInit = {}
    
    // Forward Authorization header if present
    if (authHeader) {
      headers['Authorization'] = authHeader
    }

    const { searchParams } = new URL(request.url)
    const apkId = searchParams.get('apk_id')
    const status = searchParams.get('status')
    const limit = searchParams.get('limit')

    let url = `${API_URL}/v1/apk/installations`
    const params = new URLSearchParams()
    if (apkId) params.append('apk_id', apkId)
    if (status) params.append('status', status)
    if (limit) params.append('limit', limit)
    if (params.toString()) url += `?${params.toString()}`

    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 10000)

    const response = await fetch(url, {
      headers,
      signal: controller.signal,
    })

    clearTimeout(timeoutId)

    const data = await response.json()
    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    console.error('Installation status fetch error:', error)
    return NextResponse.json({ error: 'Failed to fetch installation status' }, { status: 500 })
  }
}
