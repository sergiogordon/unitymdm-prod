package com.nexmdm

import android.content.Context
import android.util.Log
import kotlinx.coroutines.*
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.io.FileOutputStream
import java.security.MessageDigest
import java.util.concurrent.TimeUnit

class ApkDownloadManager(private val context: Context) {
    private val TAG = "NexMDM.ApkDownload"
    private val client = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .writeTimeout(60, TimeUnit.SECONDS)
        .build()
    
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private var currentJob: Job? = null

    data class DownloadProgress(
        val bytesDownloaded: Long,
        val totalBytes: Long,
        val percentComplete: Int
    )

    fun downloadApk(
        downloadUrl: String,
        deviceToken: String,
        expectedSize: Long,
        installationId: Int,
        onProgress: (DownloadProgress) -> Unit,
        onComplete: (File?, String?) -> Unit
    ) {
        currentJob?.cancel()
        
        currentJob = scope.launch {
            var retryCount = 0
            val maxRetries = 3
            var lastError: String? = null

            while (retryCount <= maxRetries && isActive) {
                if (retryCount > 0) {
                    delay(5000L * retryCount)
                }
                
                try {
                    val result = downloadWithProgress(downloadUrl, deviceToken, expectedSize, onProgress)
                    if (result != null) {
                        onComplete(result, null)
                        return@launch
                    }
                } catch (e: Exception) {
                    lastError = e.message
                    Log.w(TAG, "Download attempt ${retryCount + 1} failed: ${e.message}")
                    
                    if (e is CancellationException) throw e
                    
                    retryCount++
                }
            }

            onComplete(null, lastError ?: "Download failed after $maxRetries attempts")
        }
    }

    private suspend fun downloadWithProgress(
        downloadUrl: String,
        deviceToken: String,
        expectedSize: Long,
        onProgress: (DownloadProgress) -> Unit
    ): File? = withContext(Dispatchers.IO) {
        val request = Request.Builder()
            .url(downloadUrl)
            .addHeader("X-Device-Token", deviceToken)
            .build()

        val response = client.newCall(request).execute()
        
        if (!response.isSuccessful) {
            throw Exception("Download failed with status: ${response.code}")
        }

        val body = response.body ?: throw Exception("Response body is null")
        val contentLength = body.contentLength()
        
        if (contentLength <= 0) {
            throw Exception("Invalid content length: $contentLength")
        }

        val apkFile = File(context.cacheDir, "pending_install_${System.currentTimeMillis()}.apk")
        val inputStream = body.byteStream()
        val outputStream = FileOutputStream(apkFile)

        try {
            val buffer = ByteArray(8192)
            var bytesRead: Int
            var totalBytesRead = 0L
            var lastReportedProgress = -1

            while (inputStream.read(buffer).also { bytesRead = it } != -1) {
                if (!isActive) {
                    throw CancellationException("Download cancelled")
                }
                
                outputStream.write(buffer, 0, bytesRead)
                totalBytesRead += bytesRead

                val percentComplete = ((totalBytesRead * 100) / contentLength).toInt()
                
                // Only report progress at 25% intervals (0, 25, 50, 75, 100) to reduce backend load
                val progressMilestone = minOf((percentComplete / 25) * 25, 100)
                if (progressMilestone != lastReportedProgress && progressMilestone % 25 == 0) {
                    lastReportedProgress = progressMilestone
                    withContext(Dispatchers.Main) {
                        // Report the milestone value (0, 25, 50, 75, 100) - clamped to max 100
                        onProgress(DownloadProgress(totalBytesRead, contentLength, progressMilestone))
                    }
                }
            }

            outputStream.flush()
            
            if (expectedSize > 0 && contentLength != expectedSize) {
                apkFile.delete()
                throw Exception("Size mismatch: expected $expectedSize bytes, got $contentLength bytes")
            }

            if (totalBytesRead != contentLength) {
                apkFile.delete()
                throw Exception("Downloaded size mismatch: expected $contentLength bytes, got $totalBytesRead bytes")
            }
            
            // Ensure 100% is always reported at completion
            if (lastReportedProgress != 100) {
                withContext(Dispatchers.Main) {
                    onProgress(DownloadProgress(totalBytesRead, contentLength, 100))
                }
            }

            Log.i(TAG, "Download completed: ${apkFile.absolutePath}, size: $contentLength")
            return@withContext apkFile
        } catch (e: Exception) {
            apkFile.delete()
            throw e
        } finally {
            inputStream.close()
            outputStream.close()
        }
    }

    fun cancelDownload() {
        currentJob?.cancel()
        currentJob = null
        Log.i(TAG, "Download cancelled")
    }

    fun cleanup() {
        currentJob?.cancel()
        scope.cancel()
        
        val cacheFiles = context.cacheDir.listFiles { file ->
            file.name.startsWith("pending_install_") && file.name.endsWith(".apk")
        }
        
        cacheFiles?.forEach { file ->
            if (System.currentTimeMillis() - file.lastModified() > 3600000) {
                file.delete()
                Log.i(TAG, "Deleted old APK: ${file.name}")
            }
        }
    }
}
