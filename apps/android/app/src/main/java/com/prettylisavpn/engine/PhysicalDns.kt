package com.prettylisavpn.engine

import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import java.io.Closeable
import java.net.Inet4Address
import java.net.UnknownHostException

/** Ask Android for the preferred non-VPN network and follow Wi-Fi/mobile changes. */
internal class PhysicalDns(private val connectivity: ConnectivityManager) : Closeable {
    @Volatile private var network: Network? = null
    private val callback = object : ConnectivityManager.NetworkCallback() {
        override fun onAvailable(available: Network) { network = available }
        override fun onLost(lost: Network) { if (network == lost) network = null }
    }
    private val registered = runCatching {
        connectivity.requestNetwork(
            NetworkRequest.Builder().addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                .addCapability(NetworkCapabilities.NET_CAPABILITY_NOT_VPN).build(),
            callback,
        )
    }.isSuccess

    fun lookupIPv4(host: String): String {
        val current = network ?: return ""
        return try {
            val addresses = current.getAllByName(host)
            if (network != current) "" else addresses.filterIsInstance<Inet4Address>()
                .mapNotNull { it.hostAddress }.joinToString(" ")
        } catch (_: UnknownHostException) {
            ""
        } catch (_: SecurityException) {
            ""
        }
    }

    override fun close() {
        network = null
        if (registered) runCatching { connectivity.unregisterNetworkCallback(callback) }
    }
}
