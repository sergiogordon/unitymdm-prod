package com.nexmdm

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class NetworkMonitor(
    private val context: Context,
    private val onNetworkRegained: suspend () -> Unit
) {
    
    companion object {
        private const val TAG = "NetworkMonitor"
    }
    
    private val connectivityManager = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
    private var isRegistered = false
    private var lastNetworkValidated = false
    
    private val networkCallback = object : ConnectivityManager.NetworkCallback() {
        
        override fun onAvailable(network: Network) {
            Log.d(TAG, "net.change: state=available")
        }
        
        override fun onCapabilitiesChanged(network: Network, capabilities: NetworkCapabilities) {
            val validated = capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
            val wifi = capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)
            val cellular = capabilities.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR)
            
            val transport = when {
                wifi -> "wifi"
                cellular -> "cellular"
                else -> "other"
            }
            
            Log.d(TAG, "net.change: validated=$validated, transport=$transport")
            
            if (validated && !lastNetworkValidated) {
                Log.d(TAG, "net.regain: network became validated, triggering queue drain")
                CoroutineScope(Dispatchers.IO).launch {
                    onNetworkRegained()
                }
            }
            
            lastNetworkValidated = validated
        }
        
        override fun onLost(network: Network) {
            Log.d(TAG, "net.change: state=lost")
            lastNetworkValidated = false
        }
    }
    
    fun start() {
        if (isRegistered) {
            return
        }
        
        try {
            val request = NetworkRequest.Builder()
                .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                .build()
            
            connectivityManager.registerNetworkCallback(request, networkCallback)
            isRegistered = true
            
            lastNetworkValidated = isNetworkValidated()
            
            Log.d(TAG, "NetworkMonitor started, initial state: validated=$lastNetworkValidated")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to register network callback", e)
        }
    }
    
    fun stop() {
        if (!isRegistered) {
            return
        }
        
        try {
            connectivityManager.unregisterNetworkCallback(networkCallback)
            isRegistered = false
            Log.d(TAG, "NetworkMonitor stopped")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to unregister network callback", e)
        }
    }
    
    fun isNetworkValidated(): Boolean {
        val network = connectivityManager.activeNetwork ?: return false
        val capabilities = connectivityManager.getNetworkCapabilities(network) ?: return false
        return capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
    }
    
    fun getNetworkTransport(): String {
        val network = connectivityManager.activeNetwork ?: return "none"
        val capabilities = connectivityManager.getNetworkCapabilities(network) ?: return "none"
        
        return when {
            capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "wifi"
            capabilities.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> "cellular"
            else -> "other"
        }
    }
}
