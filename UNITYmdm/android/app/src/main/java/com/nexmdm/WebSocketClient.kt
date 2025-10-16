package com.nexmdm

import android.util.Log
import kotlinx.coroutines.*
import okhttp3.*
import okio.ByteString
import java.util.concurrent.TimeUnit

class WebSocketClient(
    private val serverUrl: String,
    private val deviceToken: String,
    private val deviceId: String
) {
    companion object {
        private const val TAG = "WebSocketClient"
        private const val RECONNECT_DELAY_MS = 3000L
        private const val MAX_FRAME_SIZE = 500 * 1024
    }

    private val client = OkHttpClient.Builder()
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .writeTimeout(10, TimeUnit.SECONDS)
        .pingInterval(30, TimeUnit.SECONDS)
        .build()

    private var webSocket: WebSocket? = null
    private var isConnected = false
    private var shouldReconnect = false
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    
    private var framesSent = 0
    private var bytesTransferred = 0L
    private var lastLogTime = 0L

    fun connect(onConnected: () -> Unit = {}, onDisconnected: () -> Unit = {}) {
        if (isConnected) {
            Log.w(TAG, "Already connected")
            return
        }

        shouldReconnect = true
        
        val wsUrl = serverUrl
            .replace("https://", "wss://")
            .replace("http://", "ws://") + "/ws/stream/device/$deviceId?token=$deviceToken"
        
        Log.i(TAG, "Connecting to WebSocket: ${wsUrl.take(50)}...")
        
        val request = Request.Builder()
            .url(wsUrl)
            .build()

        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                isConnected = true
                framesSent = 0
                bytesTransferred = 0L
                lastLogTime = System.currentTimeMillis()
                Log.i(TAG, "WebSocket connected successfully")
                onConnected()
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                Log.d(TAG, "Received text message: $text")
            }

            override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
                Log.d(TAG, "Received binary message: ${bytes.size} bytes")
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                Log.w(TAG, "WebSocket closing: code=$code, reason=$reason")
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                isConnected = false
                Log.i(TAG, "WebSocket closed: code=$code, reason=$reason")
                onDisconnected()
                
                if (shouldReconnect) {
                    scheduleReconnect(onConnected, onDisconnected)
                }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                isConnected = false
                Log.e(TAG, "WebSocket failure: ${t.message}", t)
                onDisconnected()
                
                if (shouldReconnect) {
                    scheduleReconnect(onConnected, onDisconnected)
                }
            }
        })
    }

    private fun scheduleReconnect(onConnected: () -> Unit, onDisconnected: () -> Unit) {
        Log.d(TAG, "Scheduling reconnect in ${RECONNECT_DELAY_MS}ms")
        scope.launch {
            delay(RECONNECT_DELAY_MS)
            if (shouldReconnect && !isConnected) {
                Log.d(TAG, "Attempting to reconnect...")
                connect(onConnected, onDisconnected)
            }
        }
    }

    fun sendFrame(jpegData: ByteArray, width: Int, height: Int): Boolean {
        if (!isConnected) {
            Log.w(TAG, "Cannot send frame: not connected")
            return false
        }

        if (jpegData.size > MAX_FRAME_SIZE) {
            Log.w(TAG, "Frame too large: ${jpegData.size} bytes, skipping")
            return false
        }

        val header = "$width:$height:".toByteArray()
        val frame = header + jpegData
        
        return try {
            webSocket?.send(ByteString.of(*frame)) ?: false.also {
                Log.w(TAG, "WebSocket is null")
            }
            
            framesSent++
            bytesTransferred += jpegData.size
            
            val now = System.currentTimeMillis()
            if (now - lastLogTime > 10000) {
                val fps = framesSent / ((now - lastLogTime) / 1000.0)
                val kbps = (bytesTransferred * 8) / ((now - lastLogTime) / 1000.0) / 1024
                Log.d(TAG, "Streaming stats: ${String.format("%.1f", fps)} FPS, ${String.format("%.1f", kbps)} Kbps")
                lastLogTime = now
                framesSent = 0
                bytesTransferred = 0L
            }
            
            true
        } catch (e: Exception) {
            Log.e(TAG, "Error sending frame", e)
            false
        }
    }

    fun disconnect() {
        Log.i(TAG, "Disconnecting WebSocket")
        shouldReconnect = false
        webSocket?.close(1000, "Client disconnect")
        webSocket = null
        isConnected = false
    }

    fun isConnected(): Boolean = isConnected

    fun cleanup() {
        disconnect()
        scope.cancel()
        client.dispatcher.executorService.shutdown()
    }
}
