import { NextRequest, NextResponse } from 'next/server'

const API_URL = 'http://localhost:8000'

export async function GET(request: NextRequest) {
  try {
    const token = request.headers.get('Authorization')
    
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    }
    if (token) {
      headers['Authorization'] = token
    }

    const response = await fetch(`${API_URL}/admin/settings/monitoring-defaults`, {
      method: 'GET',
      headers,
    })

    const data = await response.json()
    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    console.error('Monitoring defaults GET error:', error)
    return NextResponse.json({ error: 'Failed to fetch monitoring defaults' }, { status: 500 })
  }
}

export async function PATCH(request: NextRequest) {
  try {
    const token = request.headers.get('Authorization')
    const body = await request.json()

    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    }
    if (token) {
      headers['Authorization'] = token
    }

    const response = await fetch(`${API_URL}/admin/settings/monitoring-defaults`, {
      method: 'PATCH',
      headers,
      body: JSON.stringify(body),
    })

    const data = await response.json()
    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    console.error('Monitoring defaults PATCH error:', error)
    return NextResponse.json({ error: 'Failed to update monitoring defaults' }, { status: 500 })
  }
}
