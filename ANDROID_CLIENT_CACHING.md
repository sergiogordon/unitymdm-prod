# Android Agent APK Caching Strategy

## Overview

To achieve <1 minute APK downloads during fleet deployments, the Android agent should implement client-side APK caching based on SHA-256 hashes. This eliminates redundant downloads when the same APK version is deployed multiple times.

## Implementation Strategy

### 1. Cache Storage

Store downloaded APKs in the app's cache directory with SHA-256-based filenames:

```kotlin
// Cache directory structure
/data/data/com.nexmdm/cache/apk_cache/
  ├── {sha256_hash_1}.apk
  ├── {sha256_hash_2}.apk
  └── {sha256_hash_3}.apk
```

### 2. Cache Lookup Flow

When receiving an `install_apk` FCM message:

```kotlin
data class InstallApkMessage(
    val action: String,
    val apk_id: String,
    val installation_id: String,
    val download_url: String,
    val package_name: String,
    val version_name: String,
    val version_code: String,
    val file_size: String,
    val sha256: String  // NEW: SHA-256 hash for cache key
)

fun handleInstallApk(message: InstallApkMessage) {
    val cacheDir = File(context.cacheDir, "apk_cache")
    cacheDir.mkdirs()
    
    val cachedApk = File(cacheDir, "${message.sha256}.apk")
    
    if (cachedApk.exists() && cachedApk.length() == message.file_size.toLong()) {
        // CACHE HIT - Skip download
        Log.i(TAG, "APK cache hit: ${message.sha256}")
        installFromCache(cachedApk, message)
        reportCacheHit(message.installation_id)
    } else {
        // CACHE MISS - Download and cache
        Log.i(TAG, "APK cache miss: ${message.sha256}")
        downloadAndInstall(message, cachedApk)
    }
}
```

### 3. Download with Caching

```kotlin
suspend fun downloadAndInstall(message: InstallApkMessage, cacheFile: File) {
    val client = OkHttpClient.Builder()
        .connectionPool(ConnectionPool(5, 5, TimeUnit.MINUTES))
        .protocols(listOf(Protocol.HTTP_2, Protocol.HTTP_1_1))
        .build()
    
    val request = Request.Builder()
        .url(message.download_url)
        .header("X-Device-Token", deviceToken)
        .build()
    
    client.newCall(request).execute().use { response ->
        if (!response.isSuccessful) {
            throw IOException("Download failed: ${response.code}")
        }
        
        val tempFile = File(cacheFile.parent, "${cacheFile.name}.tmp")
        
        // Stream directly to temp file
        response.body?.byteStream()?.use { input ->
            tempFile.outputStream().use { output ->
                input.copyTo(output)
            }
        }
        
        // Verify SHA-256
        if (verifySha256(tempFile, message.sha256)) {
            tempFile.renameTo(cacheFile)
            installFromCache(cacheFile, message)
        } else {
            tempFile.delete()
            throw SecurityException("SHA-256 mismatch")
        }
    }
}
```

### 4. SHA-256 Verification

```kotlin
fun verifySha256(file: File, expectedHash: String): Boolean {
    val digest = MessageDigest.getInstance("SHA-256")
    
    file.inputStream().use { input ->
        val buffer = ByteArray(8192)
        var read: Int
        while (input.read(buffer).also { read = it } != -1) {
            digest.update(buffer, 0, read)
        }
    }
    
    val actualHash = digest.digest().joinToString("") { "%02x".format(it) }
    return actualHash.equals(expectedHash, ignoreCase = true)
}
```

### 5. Cache Management

Implement automatic cache cleanup to prevent unbounded growth:

```kotlin
fun cleanupOldCache() {
    val cacheDir = File(context.cacheDir, "apk_cache")
    val files = cacheDir.listFiles() ?: return
    
    // Sort by last modified (oldest first)
    val sortedFiles = files.sortedBy { it.lastModified() }
    
    val maxCacheSize = 500 * 1024 * 1024  // 500MB
    var currentSize = sortedFiles.sumOf { it.length() }
    
    // Evict oldest files until under limit
    for (file in sortedFiles) {
        if (currentSize <= maxCacheSize) break
        currentSize -= file.length()
        file.delete()
        Log.i(TAG, "Evicted old APK cache: ${file.name}")
    }
}
```

### 6. Status Reporting

Report cache hits back to the server for metrics:

```kotlin
fun reportCacheHit(installationId: String) {
    val reportUrl = "$baseUrl/v1/installations/$installationId/cache-hit"
    
    val request = Request.Builder()
        .url(reportUrl)
        .post(RequestBody.create(null, ""))
        .header("X-Device-Token", deviceToken)
        .build()
    
    client.newCall(request).enqueue(object : Callback {
        override fun onFailure(call: Call, e: IOException) {
            Log.w(TAG, "Failed to report cache hit: ${e.message}")
        }
        
        override fun onResponse(call: Call, response: Response) {
            Log.d(TAG, "Cache hit reported successfully")
        }
    })
}
```

## Connection Pooling Configuration

Configure OkHttp for optimal download performance:

```kotlin
val okHttpClient = OkHttpClient.Builder()
    .connectionPool(ConnectionPool(
        maxIdleConnections = 5,
        keepAliveDuration = 5,
        timeUnit = TimeUnit.MINUTES
    ))
    .protocols(listOf(Protocol.HTTP_2, Protocol.HTTP_1_1))
    .callTimeout(10, TimeUnit.MINUTES)
    .readTimeout(2, TimeUnit.MINUTES)
    .writeTimeout(2, TimeUnit.MINUTES)
    .build()
```

## Expected Performance Improvements

| Scenario | Without Caching | With Caching |
|----------|----------------|--------------|
| First download (10MB APK, 5 Mbps) | ~16 seconds | ~16 seconds |
| Re-deployment (cache hit) | ~16 seconds | <1 second |
| 100 device fleet (same APK) | 100 x 16s = 27 min | 99 x <1s + 16s = <2 min |
| Network failure retry | Full re-download | Instant from cache |

## Cache Benefits

1. **Speed**: Near-instant installation for cached APKs
2. **Bandwidth**: Saves bandwidth on re-deployments
3. **Reliability**: Survive network interruptions
4. **Cost**: Reduces object storage egress costs
5. **Scalability**: Supports rapid fleet-wide rollouts

## Security Considerations

1. **SHA-256 Verification**: All cached APKs are verified before installation
2. **Signature Checking**: Android still verifies APK signatures during installation
3. **Cache Isolation**: Cache directory is app-private, not accessible to other apps
4. **Automatic Cleanup**: Old cache entries are evicted automatically

## Monitoring

Track cache performance metrics:
- Cache hit rate (%)
- Average download time (cached vs uncached)
- Cache size (MB)
- Eviction count

Report these via telemetry to optimize cache size and TTL settings.
