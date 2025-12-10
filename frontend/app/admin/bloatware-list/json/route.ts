import { NextRequest, NextResponse } from "next/server"
import { getBackendUrl } from '@/lib/backend-url'

const BACKEND_URL = getBackendUrl('/admin/bloatware-list/json')

export async function GET(request: NextRequest) {
  try {
    const authHeader = request.headers.get("Authorization")

    const headers: HeadersInit = {
      "Content-Type": "application/json",
    }

    if (authHeader) {
      headers["Authorization"] = authHeader
    }

    const response = await fetch(`${BACKEND_URL}/admin/bloatware-list/json`, {
      headers,
    })

    if (!response.ok) {
      const error = await response.text()
      return NextResponse.json(
        { error: error || "Failed to fetch bloatware list" },
        { status: response.status }
      )
    }

    const data = await response.json()
    return NextResponse.json(data)
  } catch (error) {
    console.error("[BLOATWARE JSON] Failed to fetch list:", error)
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    )
  }
}

