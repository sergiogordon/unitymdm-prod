/**
 * Next.js API Route Proxy
 * Forwards all requests to backend on port 8000
 * This solves Replit's firewall blocking direct port access from UUID domains
 */

import { NextRequest, NextResponse } from 'next/server'

// Get backend URL with fallback - check both BACKEND_URL and NEXT_PUBLIC_BACKEND_URL
function getBackendUrl(): string {
  const backendUrl = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'
  console.log(`[Proxy] Using backend URL: ${backendUrl}`)
  return backendUrl
}

const BACKEND_URL = getBackendUrl()

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
  const startTime = Date.now()
  let backendUrl: string
  
  try {
    const path = pathSegments.join('/')
    const url = new URL(request.url)
    backendUrl = `${BACKEND_URL}/${path}${url.search}`

    console.log(`[Proxy] ${method} ${path} -> ${backendUrl}`)

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
        console.log('[Proxy] Injected admin key for admin endpoint')
      } else {
        console.warn('[Proxy] WARNING: Admin endpoint requested but ADMIN_KEY not set')
      }
    }

    // Forward request to backend with timeout
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 60000) // 60 second timeout

    let response: Response
    try {
      response = await fetch(backendUrl, {
        method,
        headers,
        body,
        signal: controller.signal,
      })
      clearTimeout(timeoutId)
    } catch (fetchError) {
      clearTimeout(timeoutId)
      
      if (fetchError instanceof Error && fetchError.name === 'AbortError') {
        console.error(`[Proxy] Request timeout after 60s: ${backendUrl}`)
        return NextResponse.json(
          { 
            error: 'Backend request timeout',
            message: 'The backend server did not respond within 60 seconds',
            backend_url: backendUrl,
            path: path
          },
          { status: 504 }
        )
      }
      
      // Check if it's a connection error
      if (fetchError instanceof Error) {
        const errorMessage = fetchError.message.toLowerCase()
        if (errorMessage.includes('econnrefused') || errorMessage.includes('failed to fetch') || errorMessage.includes('network')) {
          console.error(`[Proxy] Connection refused to backend: ${backendUrl}`, fetchError)
          return NextResponse.json(
            { 
              error: 'Backend connection failed',
              message: 'Unable to connect to backend server. Please ensure the backend is running.',
              backend_url: backendUrl,
              path: path,
              details: fetchError.message
            },
            { status: 502 }
          )
        }
      }
      
      throw fetchError
    }

    const duration = Date.now() - startTime
    console.log(`[Proxy] ${method} ${path} -> ${response.status} (${duration}ms)`)

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
    const duration = Date.now() - startTime
    console.error(`[Proxy] Error after ${duration}ms:`, error)
    console.error(`[Proxy] Backend URL: ${backendUrl || BACKEND_URL}`)
    console.error(`[Proxy] Path: ${pathSegments.join('/')}`)
    
    return NextResponse.json(
      { 
        error: 'Proxy request failed',
        message: error instanceof Error ? error.message : 'Unknown error',
        backend_url: backendUrl || BACKEND_URL,
        path: pathSegments.join('/'),
        duration_ms: duration
      },
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
