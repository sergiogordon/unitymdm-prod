import { NextRequest, NextResponse } from 'next/server';

export const runtime = 'nodejs';
export const maxDuration = 60;

export async function POST(request: NextRequest) {
  try {
    const adminKey = request.headers.get('x-admin');
    
    if (!adminKey) {
      return NextResponse.json(
        { error: 'Admin key required' },
        { status: 403 }
      );
    }

    const formData = await request.formData();
    
    const file = formData.get('file') as File;
    if (!file) {
      return NextResponse.json(
        { error: 'File is required' },
        { status: 400 }
      );
    }

    const backendFormData = new FormData();
    backendFormData.append('file', file);
    
    const fields = ['build_id', 'version_code', 'version_name', 'build_type', 'package_name'];
    for (const field of fields) {
      const value = formData.get(field);
      if (value) {
        backendFormData.append(field, value as string);
      }
    }

    const backendUrl = 'http://localhost:8000/admin/apk/upload';
    
    const response = await fetch(backendUrl, {
      method: 'POST',
      headers: {
        'X-Admin': adminKey,
      },
      body: backendFormData,
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error('Backend upload failed:', response.status, errorText);
      return NextResponse.json(
        { error: 'Upload failed', details: errorText },
        { status: response.status }
      );
    }

    const result = await response.json();
    return NextResponse.json(result, { status: 200 });

  } catch (error) {
    console.error('APK upload error:', error);
    return NextResponse.json(
      { error: 'Internal server error', details: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    );
  }
}
