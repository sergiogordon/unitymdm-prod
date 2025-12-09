import { NextRequest, NextResponse } from 'next/server'
import { isDemoRequest, handleDemoRequest } from '@/lib/apiDemoHelper'

import { getBackendUrl } from '@/lib/backend-url'

const API_URL = getBackendUrl('/v1/apk/installations')

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

    // Build URL - API_URL is already the base backend URL, append the path
    let url = `${API_URL}/v1/apk/installations`
    const params = new URLSearchParams()
    if (apkId) params.append('apk_id', apkId)
    if (status) params.append('status', status)
    if (limit) params.append('limit', limit)
    if (params.toString()) url += `?${params.toString()}`

    // Increase timeout to 30 seconds for installation queries (they can be slow during deployments)
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 30000)

    const response = await fetch(url, {
      headers,
      signal: controller.signal,
    })

    clearTimeout(timeoutId)

    if (!response.ok) {
      const errorText = await response.text()
      let errorData
      try {
        errorData = JSON.parse(errorText)
      } catch {
        errorData = { detail: errorText || 'Unknown error' }
      }
      return NextResponse.json(
        { error: errorData.detail || 'Failed to fetch installation status' },
        { status: response.status }
      )
    }

    const data = await response.json()
    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    // Handle AbortError specifically (request timeout or cancellation)
    if (error instanceof Error && error.name === 'AbortError') {
      console.error('Installation status fetch timeout')
      return NextResponse.json(
        { error: 'Request timeout - backend did not respond within 30 seconds' },
        { status: 504 }
      )
    }
    
    console.error('Installation status fetch error:', error)
    return NextResponse.json(
      { error: 'Failed to fetch installation status', details: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    )
  }
}
