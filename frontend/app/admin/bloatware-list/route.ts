import { NextRequest, NextResponse } from 'next/server'

const BACKEND_URL = 'http://localhost:8000'

export async function GET(request: NextRequest) {
  try {
    const adminKey = request.headers.get('x-admin-key') || request.headers.get('X-Admin-Key')
    
    console.log(`[BLOATWARE PROXY] Has admin key: ${!!adminKey}`)
    
    if (!adminKey) {
      console.log('[BLOATWARE PROXY] No admin key found in headers')
      return NextResponse.json(
        { error: 'Admin key required' },
        { status: 401 }
      )
    }
    
    console.log(`[BLOATWARE PROXY] Forwarding to backend`)
    
    const response = await fetch(`${BACKEND_URL}/admin/bloatware-list`, {
      headers: {
        'X-Admin-Key': adminKey,
      },
    })
    
    if (!response.ok) {
      console.log(`[BLOATWARE PROXY] Backend error: ${response.status}`)
      return new NextResponse('Failed to fetch bloatware list', {
        status: response.status,
      })
    }
    
    const text = await response.text()
    console.log(`[BLOATWARE PROXY] Successfully fetched ${text.split('\n').length} packages`)
    
    return new NextResponse(text, {
      status: 200,
      headers: {
        'Content-Type': 'text/plain',
      },
    })
  } catch (error) {
    console.error('[BLOATWARE PROXY] Error:', error)
    return new NextResponse('Failed to fetch bloatware list', {
      status: 500,
    })
  }
}
