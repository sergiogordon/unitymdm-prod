import { NextRequest, NextResponse } from 'next/server'

const API_URL = 'http://localhost:8000'

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url)
    const buildType = searchParams.get('build_type')
    const limit = searchParams.get('limit') || '50'
    const order = searchParams.get('order') || 'desc'

    const adminKey = process.env.ADMIN_KEY
    if (!adminKey) {
      return NextResponse.json(
        { error: 'Admin key not configured' },
        { status: 500 }
      )
    }

    const queryParams = new URLSearchParams()
    if (buildType) queryParams.append('build_type', buildType)
    queryParams.append('limit', limit)
    queryParams.append('order', order)

    const url = `${API_URL}/admin/apk/builds?${queryParams.toString()}`

    const response = await fetch(url, {
      headers: {
        'X-Admin': adminKey,
      },
    })

    const data = await response.json()
    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    console.error('APK builds list error:', error)
    return NextResponse.json(
      { error: 'Failed to fetch APK builds' },
      { status: 500 }
    )
  }
}

export async function DELETE(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url)
    const buildId = searchParams.get('build_id')

    if (!buildId) {
      return NextResponse.json(
        { error: 'build_id is required' },
        { status: 400 }
      )
    }

    const adminKey = process.env.ADMIN_KEY
    if (!adminKey) {
      return NextResponse.json(
        { error: 'Admin key not configured' },
        { status: 500 }
      )
    }

    const url = `${API_URL}/admin/apk/builds/${buildId}`

    const response = await fetch(url, {
      method: 'DELETE',
      headers: {
        'X-Admin': adminKey,
      },
    })

    const data = await response.json()
    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    console.error('APK build delete error:', error)
    return NextResponse.json(
      { error: 'Failed to delete APK build' },
      { status: 500 }
    )
  }
}
