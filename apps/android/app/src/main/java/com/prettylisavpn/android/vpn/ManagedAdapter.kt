package com.prettylisavpn.android.vpn

import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import com.google.gson.JsonParser
import com.prettylisavpn.android.auth.HttpAuthApi
import com.prettylisavpn.android.auth.SessionCoordinator
import com.prettylisavpn.android.network.HttpRoutes
import com.wireguard.crypto.KeyPair
import kotlinx.coroutines.*
import okhttp3.OkHttpClient
import okhttp3.Request
import java.net.Proxy
import java.time.Instant
import java.util.UUID
import java.util.concurrent.TimeUnit

internal val managedMethods = linkedMapOf("amneziawg" to "AMNEZIA", "vless_reality" to "VLESS_REALITY", "vless" to "VLESS_TLS",
    "vmess" to "VMESS_TLS", "shadowsocks2022" to "SHADOWSOCKS_2022",
    "hysteria" to "HYSTERIA1_TLS",
    "hysteria2" to "HYSTERIA2_TLS", "hysteria2_salamander" to "HYSTERIA2_SALAMANDER")

internal class ManagedAdapter(private val context: Context, private val sessions: SessionCoordinator,
    http: HttpAuthApi, override val method: VpnMethod, private val lost: () -> Unit) : ConnectionAdapter {
    private val api = ManagedApi(http, sessions)
    private val runtime = ManagedRuntime(context, lost)
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var heartbeat: Job? = null
    private var deadline: Job? = null
    private var lease: ManagedLease? = null
    private var acquired = false
    val isRunning get() = runtime.isOwned

    override suspend fun connect(country: String): ConnectionResult {
        if (!VpnPermission.request(context)) return ConnectionResult.Failed
        closeRemote()
        // The existing request binding remains a fresh public key; its private
        // half is unused by these protocols and never leaves this process.
        val publicKey = KeyPair().publicKey.toBase64()
        acquired = true
        lease = api.connect(country, publicKey, UUID.randomUUID().toString(), method.id)
        armDeadline(requireNotNull(lease))
        heartbeat = scope.launch {
            maintainLeaseHeartbeat(renew = {
                val row = api.heartbeat(requireNotNull(lease).id)
                lease = row; armDeadline(row)
                row.status in setOf("PROVISIONING", "READY") && Instant.parse(row.expires_at).isAfter(Instant.now())
            }, lost = lost, heartbeatRequired = lease?.heartbeat_required != false)
        }
        val ready = vpnDeadline(60_000) {
            while (true) {
                val row = api.get(requireNotNull(lease).id)
                if (row.status == "READY") return@vpnDeadline row
                check(row.status == "PROVISIONING"); delay(1_000)
            }
            @Suppress("UNREACHABLE_CODE") error("VPN_SETUP_FAILED")
        }
        lease = ready
        val config = requireNotNull(ready.configuration)
        val profile = config.engine_profile
        require(ready.method == method.id && profile.get("session").asString == ready.id)
        require(profile.get("country").asString == ready.country && profile.get("method").asString == managedMethods[method.id.removeSuffix("_relay")])
        require(config.expected_egress_ips.isNotEmpty())
        runtime.start(profile.toString())
        context.startForegroundService(Intent(context, TunnelForegroundService::class.java))
        val network = vpnDeadline(10_000) {
            while (true) { vpnNetwork()?.let { return@vpnDeadline it }; delay(100) }
            @Suppress("UNREACHABLE_CODE") error("VPN_NETWORK_MISSING")
        }
        HttpRoutes.vpn(network.socketFactory, object : okhttp3.Dns {
            override fun lookup(hostname: String) = network.getAllByName(hostname).toList()
        })
        val verified = verify(network, ready, config)
        return if (verified && runtime.isUp()) ConnectionResult.Verified else ConnectionResult.Failed
    }
    private suspend fun verify(network: Network, row: ManagedLease, config: ManagedConfiguration): Boolean =
        sessions.request { token -> withContext(Dispatchers.IO) {
            val client = OkHttpClient.Builder().socketFactory(network.socketFactory).proxy(Proxy.NO_PROXY)
                .dns(object : okhttp3.Dns { override fun lookup(hostname: String) = network.getAllByName(hostname).toList() })
                .followRedirects(false).followSslRedirects(false).retryOnConnectionFailure(false)
                .connectTimeout(15, TimeUnit.SECONDS).readTimeout(15, TimeUnit.SECONDS).callTimeout(25, TimeUnit.SECONDS).build()
            try {
                client.newCall(Request.Builder().url("https://api.prettylisavpn.com/vpn/sessions/${row.id}/probe")
                    .header("Authorization", "Bearer $token").header("Cache-Control", "no-store").build()).execute().use { response ->
                    check(response.isSuccessful)
                    val source = requireNotNull(response.body).source()
                    check(!source.request(4096))
                    val body = source.readUtf8()
                    val json = JsonParser.parseString(body).asJsonObject
                    json.get("verified").asBoolean && json.get("ip").asString in config.expected_egress_ips
                }
            } finally { client.connectionPool.evictAll(); client.dispatcher.executorService.shutdown() }
        } }
    @Suppress("DEPRECATION")
    private fun vpnNetwork(): Network? {
        val networks = context.getSystemService(ConnectivityManager::class.java)
        return networks.allNetworks.firstOrNull { network ->
            networks.getNetworkCapabilities(network)?.hasTransport(NetworkCapabilities.TRANSPORT_VPN) == true &&
                networks.getLinkProperties(network)?.linkAddresses?.any { it.address.hostAddress == "172.30.255.1" } == true
        }
    }
    private fun armDeadline(row: ManagedLease) {
        deadline?.cancel()
        deadline = scope.launch {
            delay((Instant.parse(row.expires_at).toEpochMilli() - System.currentTimeMillis()).coerceAtLeast(0)); lost()
        }
    }
    private suspend fun closeRemote() {
        val current = lease ?: api.current() ?: run { acquired = false; return }
        lease = current
        if (current.status != "CLOSED") {
            api.revoke(current.id)
            vpnDeadline(30_000) { while (api.get(current.id).status != "CLOSED") delay(1_000) }
        }
        lease = null; acquired = false
    }
    override suspend fun disconnect() {
        heartbeat?.cancel(); heartbeat = null; deadline?.cancel(); deadline = null
        withContext(NonCancellable) {
            disconnectCleanup(stopLocal = { try { runtime.stop() } finally { HttpRoutes.default() } },
                revokeRemote = { if (acquired || lease != null) closeRemote() })
            context.stopService(Intent(context, TunnelForegroundService::class.java))
        }
    }
}
