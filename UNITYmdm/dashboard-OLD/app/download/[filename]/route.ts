import { NextRequest, NextResponse } from 'next/server';

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ filename: string }> }
) {
  try {
    const { filename } = await params;
    
    // Proxy to FastAPI backend
    const backendUrl = `http://localhost:8000/download/${filename}`;
    const response = await fetch(backendUrl);
    
    if (!response.ok) {
      return NextResponse.json(
        { error: 'APK not found' },
        { status: 404 }
      );
    }
    
    const apkBuffer = await response.arrayBuffer();
    
    return new NextResponse(apkBuffer, {
      status: 200,
      headers: {
        'Content-Type': 'application/vnd.android.package-archive',
        'Content-Disposition': `attachment; filename="${filename}"`,
        'Content-Length': apkBuffer.byteLength.toString(),
      },
    });
  } catch (error) {
    console.error('Error downloading APK:', error);
    return NextResponse.json(
      { error: 'Failed to download APK' },
      { status: 500 }
    );
  }
}
