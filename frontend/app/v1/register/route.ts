import { NextRequest, NextResponse } from 'next/server';

export async function POST(request: NextRequest) {
  try {
    const adminKey = request.headers.get('X-Admin-Key');
    if (!adminKey) {
      return NextResponse.json(
        { detail: 'X-Admin-Key header is required' },
        { status: 401 }
      );
    }

    let body = null;
    let alias = null;
    const contentType = request.headers.get('Content-Type');
    
    if (contentType?.includes('application/json')) {
      try {
        body = await request.json();
        alias = body?.alias;
      } catch (e) {
        // Invalid JSON, fall through to check query params
      }
    }

    if (!alias) {
      const url = new URL(request.url);
      alias = url.searchParams.get('alias');
    }

    if (!alias) {
      return NextResponse.json(
        { detail: 'Alias is required in JSON body or query parameter' },
        { status: 400 }
      );
    }

    const requestBody = body || { alias };
    
    if (!requestBody.alias) {
      requestBody.alias = alias;
    }

    const backendUrl = `http://localhost:8000/v1/register`;
    const response = await fetch(backendUrl, {
      method: 'POST',
      headers: {
        'X-Admin-Key': adminKey,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(requestBody),
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
