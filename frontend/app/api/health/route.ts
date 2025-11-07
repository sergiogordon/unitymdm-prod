import { NextResponse } from 'next/server';

export async function GET() {
  return NextResponse.json(
    { 
      status: 'healthy',
      timestamp: new Date().toISOString(),
      service: 'nexmdm-frontend'
    },
    { status: 200 }
  );
}

export const dynamic = 'force-dynamic';
