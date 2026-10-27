package com.prettylisavpn.android.vpn

import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import com.google.gson.JsonParser
import com.prettylisavpn.android.auth.HttpAuthApi
import com.prettylisavpn.android.auth.SessionCoordinator
import com.wireguard.android.backend.GoBackend
import com.wireguard.android.backend.Tunnel
import com.wireguard.config.Config
import com.wireguard.crypto.KeyPair
import kotlinx.coroutines.*
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.ByteArrayInputStream
import java.net.Proxy
import java.time.Instant
import java.util.UUID
import java.util.concurrent.TimeUnit

/** Keys stay in this process; success requires fresh handshake and HTTPS through our VPN Network. */
class WireGuardAdapter(private val context: Context, private val sessions: SessionCoordinator,
    http: HttpAuthApi, private val lost: () -> Unit) : ConnectionAdapter {
    override val method = VpnMethod("wireguard", "WireGuard")
    private val api = WireGuardApi(http, sessions)
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var backend: GoBackend? = null
    private var heartbeat: Job? = null
    private var deadline: Job? = null
    private var lease: WireGuardLease? = null
    private var expectingUp = false
    val isRunning get() = expectingUp
    private var acquired = false
    // In-memory acceptance evidence only: fixed stages, counters, no keys/addresses/URLs.
    data class Diagnostic(val stage: String, val failure: String?, val httpStatus: Int?,
        val handshake: Boolean, val rxBytes: Long, val txBytes: Long)
    @Volatile private var stage = "IDLE"
    private var failure: String? = null
    private var httpStatus: Int? = null
    private var handshakeObserved = false
    private var rxBytes = 0L
    private var txBytes = 0L
    private var startedAt = 0L
    fun diagnostic() = Diagnostic(stage, failure, httpStatus, handshakeObserved, rxBytes, txBytes)
    private val tunnel = object : Tunnel {
        override fun getName() = "PrettyLisaVPN"
        override fun onStateChange(state: Tunnel.State) {
            if (state == Tunnel.State.DOWN && expectingUp) scope.launch { lost() }
        }
    }

    override suspend fun connect(country: String): ConnectionResult {
        stage = "CONSENT"; failure = null; httpStatus = null
        handshakeObserved = false; rxBytes = 0; txBytes = 0; startedAt = 0
        try {
            return connectTunnel(country)
        } catch (error: Exception) {
            failure = error.javaClass.simpleName
            throw error
        } finally {
            withContext(NonCancellable + Dispatchers.IO) {
                runCatching { backend?.getStatistics(tunnel)?.let { stats ->
                    handshakeObserved = startedAt > 0 && stats.peers().any { key -> stats.peer(key)?.latestHandshakeEpochMillis()?.let { it >= startedAt } == true }
                    rxBytes = stats.totalRx(); txBytes = stats.totalTx()
                } }
            }
        }
    }

    private suspend fun connectTunnel(country: String): ConnectionResult {
        if (!VpnPermission.request(context)) return ConnectionResult.Failed
        stage = "RECOVERY"
        // Recover an abandoned reservation from a previous process before creating a fresh key.
        closeRemote()
        val keys = KeyPair()
        stage = "PROVISIONING"
        acquired = true // A timed-out POST can still have allocated a remote peer.
        lease = api.connect(country, keys.publicKey.toBase64(), UUID.randomUUID().toString())
        armDeadline(requireNotNull(lease))
        heartbeat = scope.launch {
            while (isActive) {
                delay(30_000)
                try {
                    val row = api.heartbeat(requireNotNull(lease).id)
                    lease = row
                    armDeadline(row)
                    if (row.status !in setOf("PROVISIONING", "READY") || !Instant.parse(row.expires_at).isAfter(Instant.now())) { lost(); return@launch }
                } catch (cancel: CancellationException) { throw cancel }
                catch (_: Exception) { lost(); return@launch }
            }
        }
        val ready = withTimeout(60_000) {
            while (true) {
                val row = api.get(requireNotNull(lease).id)
                if (row.status == "READY") return@withTimeout row
                check(row.status == "PROVISIONING")
                delay(1_000)
            }
            @Suppress("UNREACHABLE_CODE") error("VPN_SETUP_FAILED")
        }
        lease = ready
        val config = requireNotNull(ready.configuration)
        require(config.allowed_ips == listOf("0.0.0.0/0", "::/0") && config.mtu in 1280..1420)
        require(config.address.matches(Regex("[0-9.]+/32")) && config.endpoint.matches(Regex("[0-9.]+:[0-9]{1,5}")))
        val text = """
            [Interface]
            PrivateKey = ${keys.privateKey.toBase64()}
            Address = ${config.address}
            DNS = ${config.dns.joinToString(", ")}
            MTU = ${config.mtu}
            [Peer]
            PublicKey = ${config.server_public_key}
            Endpoint = ${config.endpoint}
            AllowedIPs = 0.0.0.0/0, ::/0
            PersistentKeepalive = 25
        """.trimIndent()
        val parsed = Config.parse(ByteArrayInputStream(text.toByteArray(Charsets.UTF_8)))
        val started = System.currentTimeMillis() - 1_000
        startedAt = started
        stage = "START"
        withContext(Dispatchers.IO) {
            val engine = backend ?: GoBackend(context).also { backend = it }
            expectingUp = true
            engine.setState(tunnel, Tunnel.State.UP, parsed)
        }
        context.startForegroundService(Intent(context, TunnelForegroundService::class.java))
        stage = "NETWORK"
        val network = withTimeout(10_000) {
            while (true) {
                vpnNetwork(config.address.substringBefore('/'))?.let { return@withTimeout it }
                delay(100)
            }
            @Suppress("UNREACHABLE_CODE") error("VPN_NETWORK_MISSING")
        }
        // Network-bound DNS and sockets cannot silently fall back to Wi-Fi or mobile Internet.
        val verified = sessions.request { token -> withContext(Dispatchers.IO) {
            val client = OkHttpClient.Builder().socketFactory(network.socketFactory).proxy(Proxy.NO_PROXY)
                .dns(object : okhttp3.Dns {
                    override fun lookup(hostname: String): List<java.net.InetAddress> {
                        stage = "DNS"
                        return network.getAllByName(hostname).toList().also { stage = "HTTPS" }
                    }
                })
                .followRedirects(false).followSslRedirects(false).retryOnConnectionFailure(false)
                .connectTimeout(15, TimeUnit.SECONDS).readTimeout(15, TimeUnit.SECONDS).callTimeout(25, TimeUnit.SECONDS).build()
            try {
                client.newCall(Request.Builder().url("https://api.prettylisavpn.com/vpn/wireguard/sessions/${ready.id}/probe")
                    .header("Authorization", "Bearer $token").header("Cache-Control", "no-store").build()).execute().use { response ->
                    httpStatus = response.code
                    check(response.isSuccessful)
                    val body = requireNotNull(response.body).string()
                    check(body.length < 4096)
                    val json = JsonParser.parseString(body).asJsonObject
                    json.get("verified").asBoolean && json.get("ip").asString in config.expected_egress_ips
                }
            } finally { client.connectionPool.evictAll(); client.dispatcher.executorService.shutdown() }
        } }
        stage = if (verified) "HANDSHAKE" else "EGRESS_MISMATCH"
        val handshake = withContext(Dispatchers.IO) {
            val stats = requireNotNull(backend).getStatistics(tunnel)
            stats.peers().any { key -> stats.peer(key)?.latestHandshakeEpochMillis()?.let { it >= started } == true }
        }
        return if (verified && handshake && expectingUp) {
            stage = "VERIFIED"
            ConnectionResult.Verified
        } else ConnectionResult.Failed
    }

    @Suppress("DEPRECATION") // Enumerate VPN networks and match our exact allocated address.
    private fun vpnNetwork(address: String): Network? {
        val manager = context.getSystemService(ConnectivityManager::class.java)
        return manager.allNetworks.firstOrNull { network ->
            manager.getNetworkCapabilities(network)?.hasTransport(NetworkCapabilities.TRANSPORT_VPN) == true &&
                manager.getLinkProperties(network)?.linkAddresses?.any { it.address.hostAddress == address } == true
        }
    }

    private fun armDeadline(row: WireGuardLease) {
        deadline?.cancel()
        deadline = scope.launch {
            delay((Instant.parse(row.expires_at).toEpochMilli() - System.currentTimeMillis()).coerceAtLeast(0))
            lost()
        }
    }

    private suspend fun closeRemote() {
        val current = lease ?: api.current() ?: return
        lease = current
        if (current.status != "CLOSED") {
            api.revoke(current.id)
            withTimeout(30_000) { while (api.get(current.id).status != "CLOSED") delay(1_000) }
        }
        lease = null
        acquired = false
    }

    override suspend fun disconnect() {
        heartbeat?.cancel(); heartbeat = null
        deadline?.cancel(); deadline = null
        expectingUp = false
        withContext(Dispatchers.IO) { backend?.setState(tunnel, Tunnel.State.DOWN, null) }
        context.stopService(Intent(context, TunnelForegroundService::class.java))
        if (acquired || lease != null) closeRemote()
    }
}
