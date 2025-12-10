/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  eslint: {
    ignoreDuringBuilds: true,
  },
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  // Increase body size limit for APK uploads (500MB)
  experimental: {
    serverActions: {
      bodySizeLimit: '500mb',
    },
  },
  // Allow cross-origin requests from Replit domains
  allowedDevOrigins: [
    '*.replit.dev',
    '*.worf.replit.dev',
    '*.picard.replit.dev',
    '*.repl.co',
  ],
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          {
            key: 'Cache-Control',
            value: 'no-cache, no-store, must-revalidate',
          },
        ],
      },
    ]
  },
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
