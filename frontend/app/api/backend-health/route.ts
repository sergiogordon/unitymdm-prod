import { NextRequest, NextResponse } from 'next/server'
import { checkBackendHealth } from '@/lib/backend-health'

/**
 * Backend Health Check API Route
 * Proxies health check requests to backend and returns structured status
 */
export async function GET(request: NextRequest) {
  try {
    // Use proxy to check backend health
    const healthStatus = await checkBackendHealth(true, 5000)

    // Return appropriate HTTP status based on backend status
    const httpStatus = healthStatus.status === 'running' ? 200 : 503

    return NextResponse.json(healthStatus, { status: httpStatus })
  } catch (error) {
    console.error('[Backend Health API] Error:', error)
    return NextResponse.json(
      {
        status: 'error',
        message: 'Failed to check backend health',
        error: error instanceof Error ? error.message : 'unknown',
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
      'Access-Control-Allow-Methods': 'GET, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
    },
  })
}

