/**
 * Next.js API Route Proxy
 * Forwards all requests to backend on port 8000
 * This solves Replit's firewall blocking direct port access from UUID domains
 */

import { NextRequest, NextResponse } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params
  return proxyRequest(request, path, 'GET')
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params
  return proxyRequest(request, path, 'POST')
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params
  return proxyRequest(request, path, 'PUT')
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params
  return proxyRequest(request, path, 'DELETE')
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params
  return proxyRequest(request, path, 'PATCH')
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

    // Get request body for POST/PUT/PATCH first to determine if it's FormData
    let body: ArrayBuffer | FormData | undefined = undefined
    let isFormData = false
    if (method !== 'GET' && method !== 'DELETE') {
      try {
        // Check if this is a multipart form-data request
        const contentType = request.headers.get('content-type') || ''
        if (contentType.includes('multipart/form-data')) {
          // For multipart/form-data, we need to get the formData and reconstruct it
          // because we can't directly forward the boundary
          const formData = await request.formData()
          body = formData
          isFormData = true
        } else {
          // For other content types, use arrayBuffer to preserve binary data
          body = await request.arrayBuffer()
        }
      } catch (e) {
        // No body or already consumed
        console.error('[Proxy] Error reading request body:', e)
      }
    }

    // Forward headers
    const headers = new Headers()
    request.headers.forEach((value, key) => {
      // Skip Next.js internal headers (but allow X-Admin and other custom headers)
      const isNextJsHeader = key.startsWith('x-nextjs-') || key.startsWith('x-middleware-')
      // Skip content-type and content-length for FormData as fetch will set them correctly
      const skipHeader = isNextJsHeader || key === 'host' || key === 'connection' || 
                         (isFormData && (key === 'content-type' || key === 'content-length'))
      if (!skipHeader) {
        headers.set(key, value)
      }
    })

    // Inject admin key for admin endpoints (server-side only, for security)
    if (path.startsWith('admin/')) {
      const adminKey = process.env.ADMIN_KEY
      if (adminKey) {
        headers.set('X-Admin', adminKey)
      }
    }

    // Forward request to backend
    const response = await fetch(backendUrl, {
      method,
      headers,
      body,
    })

    // Stream the response body to preserve binary data (APK files, etc.)
    const responseBody = await response.arrayBuffer()

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

    return new NextResponse(responseBody, {
      status: response.status,
      headers: responseHeaders,
    })
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
