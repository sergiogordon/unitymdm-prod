import { NextRequest, NextResponse } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'

export async function GET(request: NextRequest) {
  try {
    const url = new URL(request.url)
    const backendUrl = `${BACKEND_URL}/admin/settings/wifi${url.search}`

    const headers = new Headers()
    request.headers.forEach((value, key) => {
      const isNextJsHeader = key.startsWith('x-nextjs-') || key.startsWith('x-middleware-')
      if (!isNextJsHeader && key !== 'host' && key !== 'connection') {
        headers.set(key, value)
      }
    })

    const response = await fetch(backendUrl, {
      method: 'GET',
      headers,
    })

    const responseBody = await response.text()

    const responseHeaders = new Headers()
    response.headers.forEach((value, key) => {
      if (key !== 'transfer-encoding' && key !== 'connection') {
        responseHeaders.set(key, value)
      }
    })

    responseHeaders.set('Access-Control-Allow-Origin', '*')
    responseHeaders.set('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
    responseHeaders.set('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Admin-Key')

    return new NextResponse(responseBody, {
      status: response.status,
      headers: responseHeaders,
    })
  } catch (error) {
    console.error('[Admin WiFi Settings Proxy] Error:', error)
    return NextResponse.json(
      { error: 'Proxy request failed', details: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    )
  }
}

export async function OPTIONS() {
  return new NextResponse(null, {
    status: 200,
    headers: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Admin-Key',
    },
  })
}

