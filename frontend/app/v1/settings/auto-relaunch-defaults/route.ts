import { NextRequest, NextResponse } from 'next/server'

import { getBackendUrl } from '@/lib/backend-url'

export async function GET(request: NextRequest) {
  try {
    // Resolve backend URL dynamically on each request
    const API_URL = getBackendUrl('/v1/settings/auto-relaunch-defaults')
    
    const token = request.headers.get('Authorization')
    
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    }
    if (token) {
      headers['Authorization'] = token
    }

    const response = await fetch(`${API_URL}/admin/settings/auto-relaunch-defaults`, {
      method: 'GET',
      headers,
    })

    const data = await response.json()
    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    console.error('Auto relaunch defaults GET error:', error)
    return NextResponse.json({ error: 'Failed to fetch auto relaunch defaults' }, { status: 500 })
  }
}

export async function PATCH(request: NextRequest) {
  try {
    // Resolve backend URL dynamically on each request
    const API_URL = getBackendUrl('/v1/settings/auto-relaunch-defaults')
    
    const token = request.headers.get('Authorization')
    const body = await request.json()

    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    }
    if (token) {
      headers['Authorization'] = token
    }

    const response = await fetch(`${API_URL}/admin/settings/auto-relaunch-defaults`, {
      method: 'PATCH',
      headers,
      body: JSON.stringify(body),
    })

    const data = await response.json()
    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    console.error('Auto relaunch defaults PATCH error:', error)
    return NextResponse.json({ error: 'Failed to update auto relaunch defaults' }, { status: 500 })
  }
}

