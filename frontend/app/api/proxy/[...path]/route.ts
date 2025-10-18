/**
 * Next.js API Route Proxy
 * Forwards all requests to backend on port 8000
 * This solves Replit's firewall blocking direct port access from UUID domains
 */

import { NextRequest, NextResponse } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'

export async function GET(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params.path, 'GET')
}

export async function POST(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params.path, 'POST')
}

export async function PUT(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params.path, 'PUT')
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params.path, 'DELETE')
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params.path, 'PATCH')
}

async function proxyRequest(
  request: NextRequest,
  pathSegments: string[],
  method: string
) {
  try {
    const path = pathSegments.join('/')
    const url = new URL(request.url)
    const backendUrl = `${BACKEND_URL}/${path}${url.search}`

    console.log(`[Proxy] ${method} ${path} -> ${backendUrl}`)

    // Forward headers
    const headers = new Headers()
    request.headers.forEach((value, key) => {
      // Skip Next.js internal headers and host header
      if (!key.startsWith('x-') && key !== 'host' && key !== 'connection') {
        headers.set(key, value)
      }
    })

    // Get request body for POST/PUT/PATCH
    let body = undefined
    if (method !== 'GET' && method !== 'DELETE') {
      try {
        body = await request.text()
      } catch (e) {
        // No body or already consumed
      }
    }

    // Forward request to backend
    const response = await fetch(backendUrl, {
      method,
      headers,
      body,
    })

    // Get response body
    const responseText = await response.text()
    let responseData
    try {
      responseData = JSON.parse(responseText)
    } catch {
      responseData = responseText
    }

    // Forward response headers
    const responseHeaders = new Headers()
    response.headers.forEach((value, key) => {
      // Skip headers that might cause issues
      if (key !== 'transfer-encoding' && key !== 'connection') {
        responseHeaders.set(key, value)
      }
    })

    // Add CORS headers
    responseHeaders.set('Access-Control-Allow-Origin', '*')
    responseHeaders.set('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, PATCH, OPTIONS')
    responseHeaders.set('Access-Control-Allow-Headers', 'Content-Type, Authorization')

    return new NextResponse(
      typeof responseData === 'string' ? responseData : JSON.stringify(responseData),
      {
        status: response.status,
        headers: responseHeaders,
      }
    )
  } catch (error) {
    console.error('[Proxy] Error:', error)
    return NextResponse.json(
      { error: 'Proxy request failed', details: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    )
  }
}

// Handle OPTIONS for CORS
export async function OPTIONS() {
  return new NextResponse(null, {
    status: 200,
    headers: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, PATCH, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    },
  })
}
