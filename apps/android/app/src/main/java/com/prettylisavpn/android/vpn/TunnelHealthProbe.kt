package com.prettylisavpn.android.vpn

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.os.PowerManager
import com.google.gson.JsonObject
import com.google.gson.JsonParser
import kotlinx.coroutines.*
import okhttp3.*
import java.io.IOException
import java.net.Proxy
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume

/** Fixed anonymous requests only; no account credentials, browsing destinations or logs. */
internal class TunnelHealthProbe(
    private val client: OkHttpClient,
    private val ipUrl: String = "https://ifconfig.me/all.json",
    private val apiUrl: String = "https://api.prettylisavpn.com/version",
) {
    private data class Observation(val body: JsonObject? = null, val transportFailed: Boolean = false)
    private suspend fun read(url: String): Observation = suspendCancellableCoroutine { continuation ->
        val call = client.newCall(Request.Builder().url(url).header("Accept", "application/json").header("Cache-Control", "no-store").build())
        continuation.invokeOnCancellation { call.cancel() }
        call.enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) { continuation.resume(Observation(transportFailed = true)) }
            override fun onResponse(call: Call, response: Response) {
                val result = response.use {
                    if (!it.isSuccessful) Observation() else try {
                        val source = it.body?.source()
                        if (source == null || source.request(4097)) Observation()
                        else Observation(runCatching { JsonParser.parseString(source.readUtf8()).asJsonObject }.getOrNull())
                    } catch (_: IOException) { Observation(transportFailed = true) }
                }
                continuation.resume(result)
            }
        })
    }
    suspend fun check(expectedIps: List<String>): TunnelHealth {
        if (expectedIps.isEmpty()) return TunnelHealth.UNKNOWN
        val primary = read(ipUrl)
        currentCoroutineContext().ensureActive()
        val observed = primary.body?.get("ip_addr")?.takeIf { it.isJsonPrimitive && it.asJsonPrimitive.isString }?.asString
        val validIp = observed != null && observed.matches(Regex("[0-9]{1,3}(\\.[0-9]{1,3}){3}")) && observed.split('.').all { it.toInt() in 0..255 }
        if (validIp) return if (observed in expectedIps) TunnelHealth.HEALTHY else TunnelHealth.UNREACHABLE
        // Both origins are mandatory VPN routes in split mode. An unavailable
        // metadata provider alone must not cycle a working tunnel.
        val secondary = read(apiUrl)
        val version = secondary.body?.get("application_version")?.takeIf { it.isJsonPrimitive && it.asJsonPrimitive.isString }?.asString
        if (!version.isNullOrBlank() && version.length <= 256) return TunnelHealth.HEALTHY
        return if (primary.transportFailed && secondary.transportFailed) TunnelHealth.UNREACHABLE else TunnelHealth.UNKNOWN
    }
}

/** A missing physical network suspends recovery; it is not evidence against a method. */
@Suppress("DEPRECATION")
internal fun underlyingNetworkAvailable(context: Context, validated: Boolean = false): Boolean {
    val manager = context.getSystemService(ConnectivityManager::class.java)
    return manager.allNetworks.any { network -> manager.getNetworkCapabilities(network)?.let {
        it.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_VPN) &&
            it.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
            (!validated || it.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED))
    } == true }
}

internal fun healthWithUplink(result: TunnelHealth, present: Boolean, validated: Boolean): TunnelHealth =
    if (!present || (result == TunnelHealth.UNREACHABLE && !validated)) TunnelHealth.NO_NETWORK else result

internal suspend fun checkTunnelNetwork(context: Context, network: Network?, expectedIps: List<String>, isUp: suspend () -> Boolean): TunnelHealth {
    fun sleeping() = context.getSystemService(PowerManager::class.java).isDeviceIdleMode
    if (sleeping()) return TunnelHealth.SUSPENDED
    if (!underlyingNetworkAvailable(context)) return TunnelHealth.NO_NETWORK
    val up = try { isUp() } catch (cancel: CancellationException) { throw cancel } catch (_: Exception) { false }
    if (network == null || !up) return healthWithUplink(TunnelHealth.UNREACHABLE, underlyingNetworkAvailable(context), underlyingNetworkAvailable(context, true))
    return withContext(Dispatchers.IO) {
        val client = OkHttpClient.Builder().socketFactory(network.socketFactory).proxy(Proxy.NO_PROXY)
            .dns(object : Dns { override fun lookup(hostname: String) = network.getAllByName(hostname).toList() })
            .followRedirects(false).followSslRedirects(false).retryOnConnectionFailure(false)
            .connectTimeout(4, TimeUnit.SECONDS).readTimeout(4, TimeUnit.SECONDS).callTimeout(6, TimeUnit.SECONDS).build()
        try {
            val result = TunnelHealthProbe(client).check(expectedIps)
            if (sleeping()) TunnelHealth.SUSPENDED else healthWithUplink(result, underlyingNetworkAvailable(context), underlyingNetworkAvailable(context, true))
        } finally {
            client.connectionPool.evictAll(); client.dispatcher.executorService.shutdown()
        }
    }
}
