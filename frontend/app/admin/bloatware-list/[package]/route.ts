import { NextRequest, NextResponse } from "next/server"
import { getBackendUrl } from '@/lib/backend-url'

export async function DELETE(
  request: NextRequest,
  { params }: { params: { package: string } }
) {
  try {
    // Resolve backend URL dynamically on each request
    const BACKEND_URL = getBackendUrl('/admin/bloatware-list')
    
    const authHeader = request.headers.get("Authorization")
    const packageName = params.package

    if (!packageName) {
      return NextResponse.json(
        { error: "Package name is required" },
        { status: 400 }
      )
    }

    const headers: HeadersInit = {
      "Content-Type": "application/json",
    }

    if (authHeader) {
      headers["Authorization"] = authHeader
    }

    const response = await fetch(
      `${BACKEND_URL}/admin/bloatware-list/${encodeURIComponent(packageName)}`,
      {
        method: "DELETE",
        headers,
      }
    )

    if (!response.ok) {
      const error = await response.text()
      return NextResponse.json(
        { error: error || "Failed to delete package" },
        { status: response.status }
      )
    }

    const data = await response.json().catch(() => ({ ok: true }))
    return NextResponse.json(data)
  } catch (error) {
    console.error("[BLOATWARE DELETE] Failed:", error)
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    )
  }
}

