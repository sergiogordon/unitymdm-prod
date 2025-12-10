import { NextRequest, NextResponse } from 'next/server';
import { getBackendUrl } from '@/lib/backend-url';

export async function POST(request: NextRequest) {
  try {
    // Resolve backend URL dynamically on each request
    const BACKEND_URL = getBackendUrl('/v1/heartbeat');
    
    const authHeader = request.headers.get('Authorization');
    
    if (!authHeader) {
      return NextResponse.json(
        { detail: 'Authorization header is required' },
        { status: 401 }
      );
    }

    const body = await request.json();

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 60000);

    const response = await fetch(`${BACKEND_URL}/v1/heartbeat`, {
      method: 'POST',
      headers: {
        'Authorization': authHeader,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      // Handle non-JSON error responses (e.g., rate limit plain text)
      const contentType = response.headers.get('content-type');
      let errorData;
      
      if (contentType && contentType.includes('application/json')) {
        try {
          errorData = await response.json();
        } catch {
          errorData = { detail: 'Unknown error' };
        }
      } else {
        // Plain text response (e.g., "Rate exceeded.")
        const errorText = await response.text();
        errorData = { detail: errorText || `HTTP ${response.status}: ${response.statusText}` };
      }
      
      return NextResponse.json(errorData, { status: response.status });
    }

    const data = await response.json();
    return NextResponse.json(data, { status: 200 });
  } catch (error) {
    console.error('Error proxying heartbeat:', error);
    
    // Handle JSON parse errors specifically
    if (error instanceof SyntaxError && error.message.includes('JSON')) {
      return NextResponse.json(
        { detail: 'Invalid response from backend server' },
        { status: 502 }
      );
    }
    
    return NextResponse.json(
      { detail: 'Failed to process heartbeat' },
      { status: 500 }
    );
  }
}
