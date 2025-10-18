import { NextRequest, NextResponse } from 'next/server';

export async function POST(request: NextRequest) {
  try {
    const url = new URL(request.url);
    const alias = url.searchParams.get('alias');
    
    if (!alias) {
      return NextResponse.json(
        { detail: 'Alias parameter is required' },
        { status: 400 }
      );
    }

    const adminKey = request.headers.get('X-Admin');
    if (!adminKey) {
      return NextResponse.json(
        { detail: 'X-Admin header is required' },
        { status: 401 }
      );
    }

    let body = null;
    const contentType = request.headers.get('Content-Type');
    
    if (contentType?.includes('application/json')) {
      try {
        body = await request.json();
      } catch (e) {
        // No body or invalid JSON, proceed without body
      }
    }

    const backendUrl = `http://localhost:8000/v1/register?alias=${encodeURIComponent(alias)}`;
    const response = await fetch(backendUrl, {
      method: 'POST',
      headers: {
        'X-Admin': adminKey,
        'Content-Type': 'application/json',
      },
      body: body ? JSON.stringify(body) : undefined,
    });

    if (!response.ok) {
      const error = await response.json();
      return NextResponse.json(error, { status: response.status });
    }

    const data = await response.json();
    return NextResponse.json(data, { status: 200 });
  } catch (error) {
    console.error('Error proxying registration:', error);
    return NextResponse.json(
      { detail: 'Failed to register device' },
      { status: 500 }
    );
  }
}
