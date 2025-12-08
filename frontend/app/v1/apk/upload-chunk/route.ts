import { NextRequest, NextResponse } from 'next/server'
import { cookies } from 'next/headers'

const API_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'

export async function POST(request: NextRequest) {
  try {
    const cookieStore = await cookies()
    const sessionCookie = cookieStore.get('session_token')
    const authHeader = request.headers.get('authorization')

    const incomingFormData = await request.formData()

    // Extract the file blob and form fields
    const file = incomingFormData.get('file') as File | null
    const uploadId = incomingFormData.get('upload_id') as string | null
    const chunkIndex = incomingFormData.get('chunk_index') as string | null
    const totalChunks = incomingFormData.get('total_chunks') as string | null
    const filename = incomingFormData.get('filename') as string | null

    // Validate required fields - check for null, empty strings, and invalid numeric values
    if (!file || !uploadId || !uploadId.trim() || !filename || !filename.trim()) {
      console.error('APK chunk upload error: Missing required fields', {
        hasFile: !!file,
        uploadId,
        filename
      })
      return NextResponse.json({ error: 'Missing required fields' }, { status: 400 })
    }

    if (!chunkIndex || !chunkIndex.trim() || !totalChunks || !totalChunks.trim()) {
      console.error('APK chunk upload error: Missing or invalid chunk index/total chunks', {
        chunkIndex,
        totalChunks
      })
      return NextResponse.json({ error: 'Missing or invalid chunk index/total chunks' }, { status: 400 })
    }

    // Validate that chunkIndex and totalChunks are valid numbers
    const chunkIndexNum = parseInt(chunkIndex, 10)
    const totalChunksNum = parseInt(totalChunks, 10)
    if (isNaN(chunkIndexNum) || isNaN(totalChunksNum) || chunkIndexNum < 0 || totalChunksNum <= 0 || chunkIndexNum >= totalChunksNum) {
      console.error('APK chunk upload error: Invalid numeric values for chunk index/total chunks', {
        chunkIndex,
        totalChunks,
        chunkIndexNum,
        totalChunksNum,
        invalidRange: chunkIndexNum >= totalChunksNum
      })
      return NextResponse.json({ error: 'Invalid numeric values for chunk index/total chunks' }, { status: 400 })
    }

    // Reconstruct FormData with the file blob properly included
    const formData = new FormData()
    formData.append('file', file)
    formData.append('upload_id', uploadId)
    formData.append('chunk_index', chunkIndex)
    formData.append('total_chunks', totalChunks)
    formData.append('filename', filename)

    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 120000)

    const headers: Record<string, string> = {}
    
    if (authHeader) {
      headers['Authorization'] = authHeader
    } else if (sessionCookie) {
      headers['Cookie'] = `session_token=${sessionCookie.value}`
    }

    console.log('Forwarding chunk upload to backend', {
      uploadId,
      chunkIndex,
      totalChunks,
      filename,
      fileSize: file.size
    })

    const response = await fetch(`${API_URL}/v1/apk/upload-chunk`, {
      method: 'POST',
      headers,
      body: formData,
      signal: controller.signal,
    })

    clearTimeout(timeoutId)

    if (!response.ok) {
      const errorText = await response.text()
      console.error('Backend chunk upload error:', {
        status: response.status,
        statusText: response.statusText,
        error: errorText
      })
      return NextResponse.json(
        { error: `Backend error: ${response.statusText}`, details: errorText },
        { status: response.status }
      )
    }

    const data = await response.json()
    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    console.error('APK chunk upload error:', error)
    const errorMessage = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json(
      { error: 'Failed to upload chunk', details: errorMessage },
      { status: 500 }
    )
  }
}
