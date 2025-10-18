package com.nexmdm

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.util.Log

class NetworkMonitor(context: Context) {
    
    companion object {
        private const val TAG = "NetworkMonitor"
    }
    
    private val connectivityManager = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
    private var networkCallback: ConnectivityManager.NetworkCallback? = null
    private var onNetworkAvailableCallback: (() -> Unit)? = null
    
    private var lastTransport: String = "none"
    private var lastValidated: Boolean = false
    
    fun start(onNetworkAvailable: () -> Unit) {
        if (networkCallback != null) {
            Log.w(TAG, "NetworkMonitor already started")
            return
        }
        
        this.onNetworkAvailableCallback = onNetworkAvailable
        
        val initialState = getCurrentNetworkState()
        lastTransport = initialState.transport
        lastValidated = initialState.validated
        
        Log.i(TAG, "[net.monitor.start] transport=${initialState.transport} validated=${initialState.validated}")
        
        val networkRequest = NetworkRequest.Builder()
            .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
            .build()
        
        networkCallback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                val state = getNetworkState(network)
                Log.i(TAG, "[net.available] transport=${state.transport} validated=${state.validated}")
            }
            
            override fun onCapabilitiesChanged(
                network: Network,
                capabilities: NetworkCapabilities
            ) {
                val newState = getNetworkState(network, capabilities)
                val oldTransport = lastTransport
                val oldValidated = lastValidated
                
                lastTransport = newState.transport
                lastValidated = newState.validated
                
                Log.i(TAG, "[net.change] old=$oldTransport→${newState.transport} validated=$oldValidated→${newState.validated}")
                
                if (newState.validated && !oldValidated) {
                    Log.i(TAG, "[net.regain] triggering queue drain")
                    onNetworkAvailableCallback?.invoke()
                }
            }
            
            override fun onLost(network: Network) {
                lastTransport = "none"
                lastValidated = false
                Log.w(TAG, "[net.lost] network unavailable")
            }
        }
        
        connectivityManager.registerNetworkCallback(networkRequest, networkCallback!!)
    }
    
    fun stop() {
        networkCallback?.let { callback ->
            connectivityManager.unregisterNetworkCallback(callback)
            networkCallback = null
            Log.i(TAG, "[net.monitor.stop]")
        }
    }
    
    fun getCurrentNetworkState(): NetworkState {
        val network = connectivityManager.activeNetwork
        return if (network != null) {
            val capabilities = connectivityManager.getNetworkCapabilities(network)
            getNetworkState(network, capabilities)
        } else {
            NetworkState(transport = "none", validated = false, ssid = null, carrier = null)
        }
    }
    
    private fun getNetworkState(
        network: Network,
        capabilities: NetworkCapabilities? = null
    ): NetworkState {
        val caps = capabilities ?: connectivityManager.getNetworkCapabilities(network)
        
        val transport = when {
            caps?.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) == true -> "wifi"
            caps?.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) == true -> "cell"
            caps?.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) == true -> "ethernet"
            else -> "unknown"
        }
        
        val validated = caps?.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED) == true
        
        return NetworkState(
            transport = transport,
            validated = validated,
            ssid = null,
            carrier = null
        )
    }
    
    data class NetworkState(
        val transport: String,
        val validated: Boolean,
        val ssid: String?,
        val carrier: String?
    )
}
