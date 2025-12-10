import { NextRequest, NextResponse } from 'next/server';

import { getBackendUrl } from '@/lib/backend-url'

export async function POST(request: NextRequest) {
  try {
    // Resolve backend URL dynamically on each request
    const BACKEND_URL = getBackendUrl('/v1/remote-exec/ack');
    
    const deviceToken = request.headers.get('X-Device-Token');
    
    if (!deviceToken) {
      return NextResponse.json(
        { detail: 'X-Device-Token header is required' },
        { status: 401 }
      );
    }

    const body = await request.json();

    const response = await fetch(`${BACKEND_URL}/v1/remote-exec/ack`, {
      method: 'POST',
      headers: {
        'X-Device-Token': deviceToken,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const error = await response.json();
      return NextResponse.json(error, { status: response.status });
    }

    const data = await response.json();
    return NextResponse.json(data, { status: 200 });
  } catch (error) {
    console.error('Error proxying remote-exec ACK:', error);
    return NextResponse.json(
      { detail: 'Failed to process remote-exec ACK' },
      { status: 500 }
    );
  }
}
