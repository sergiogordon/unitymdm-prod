import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

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
    
    const file = formData.get('file');
    const buildId = formData.get('build_id');
    const versionCode = formData.get('version_code');
    const versionName = formData.get('version_name');
    const buildType = formData.get('build_type');
    const packageName = formData.get('package_name');

    if (!file || !(file instanceof File)) {
      return NextResponse.json(
        { error: 'APK file is required' },
        { status: 400 }
      );
    }

    if (!versionCode || !versionName) {
      return NextResponse.json(
        { error: 'Missing required fields: version_code, version_name' },
        { status: 400 }
      );
    }

    console.log(`[APK Upload Proxy] Uploading ${file.name} (${file.size} bytes) to backend...`);
    console.log(`[APK Upload Proxy] Version: ${versionName} (${versionCode}), Type: ${buildType || 'release'}`);
    console.log(`[APK Upload Proxy] Build ID: ${buildId || 'N/A'}`);

    // Backend expects 'apk_file' not 'file'
    const backendFormData = new FormData();
    backendFormData.append('apk_file', file);
    backendFormData.append('version_code', versionCode.toString());
    backendFormData.append('version_name', versionName.toString());
    // Description includes build metadata for traceability
    const description = `CI Build: ${buildId || 'manual'}, Type: ${buildType || 'release'}, Package: ${packageName || 'com.nexmdm'}`;
    backendFormData.append('description', description);
    backendFormData.append('enabled', 'true');

    // Backend expects 'X-Admin-Key' not 'X-Admin'
    const backendResponse = await fetch(`${BACKEND_URL}/admin/apk/upload`, {
      method: 'POST',
      headers: {
        'X-Admin-Key': adminKey,
      },
      body: backendFormData,
    });

    const rawBody = await backendResponse.text();
    let responseData: any;

    const contentType = backendResponse.headers.get('content-type');
    if (contentType && contentType.includes('application/json')) {
      try {
        responseData = JSON.parse(rawBody);
      } catch (jsonError) {
        console.error('[APK Upload Proxy] Failed to parse JSON response:', jsonError);
        responseData = { error: 'Invalid JSON response from backend', body: rawBody };
      }
    } else {
      responseData = { message: rawBody };
    }

    if (!backendResponse.ok) {
      console.error(`[APK Upload Proxy] Backend error: ${backendResponse.status}`, responseData);
      return NextResponse.json(
        responseData,
        { status: backendResponse.status }
      );
    }

    console.log(`[APK Upload Proxy] Upload successful: ${file.name}`);
    return NextResponse.json(responseData, { status: 200 });

  } catch (error) {
    console.error('[APK Upload Proxy] Error:', error);
    return NextResponse.json(
      { 
        error: 'Failed to upload APK file',
        details: error instanceof Error ? error.message : 'Unknown error'
      },
      { status: 500 }
    );
  }
}
