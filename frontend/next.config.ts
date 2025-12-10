import type { NextConfig } from "next"

const nextConfig: NextConfig = {
  async rewrites() {
    // Use BACKEND_URL from environment, fallback to localhost for development
    const backendUrl = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'
    // Remove trailing slash if present
    const normalizedBackendUrl = backendUrl.replace(/\/$/, '')
    
    return [
      {
        source: "/v1/:path*",
        destination: `${normalizedBackendUrl}/v1/:path*`,
      },
    ]
  },
}

export default nextConfig
