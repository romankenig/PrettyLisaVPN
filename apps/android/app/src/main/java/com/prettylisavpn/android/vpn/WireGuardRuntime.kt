package com.prettylisavpn.android.vpn

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import com.wireguard.android.backend.GoBackend
import com.wireguard.android.backend.Tunnel
import com.wireguard.config.Config
import com.wireguard.config.InetEndpoint
import com.wireguard.config.InetNetwork
import com.wireguard.config.Interface
import com.wireguard.config.Peer
import com.wireguard.crypto.Key
import com.wireguard.crypto.KeyPair
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import okhttp3.ConnectionPool
import okhttp3.Dns
import okhttp3.OkHttpClient
import okhttp3.Request
import java.net.Inet4Address
import java.util.concurrent.TimeUnit

internal class WireGuardKey : TunnelKey {
    val pair = KeyPair()
    override val publicKey: String get() = pair.publicKey.toBase64()
    override fun toString() = "WireGuardKey([redacted])"
}

/** Called only from PrettyVpnService, whose superclass supplies GoBackend's service future.
 * No second VpnService, protected probe socket or process-wide network binding is used.
 */
internal class WireGuardRuntime(private val context: Context, private val lost: () -> Unit) : TunnelRuntime {
    private val mutex = Mutex()
    private var backend: GoBackend? = null
    @Volatile private var stopping = false
    private val tunnel = object : Tunnel {
        override fun getName() = "PrettyLisaVPN"
        override fun onStateChange(state: Tunnel.State) { if (state == Tunnel.State.DOWN && !stopping) lost() }
    }
    override suspend fun start(config: VpnConfig, key: TunnelKey) = withContext(Dispatchers.IO) {
        mutex.withLock {
            val secret = (key as? WireGuardKey)?.pair ?: throw VpnFailure(VpnError.STORAGE)
            val iface = Interface.Builder().setKeyPair(secret).addAddress(InetNetwork.parse(config.address))
                .setMtu(config.mtu).apply { config.dns.forEach { addDnsServer(java.net.InetAddress.getByName(it)) } }.build()
            val peer = Peer.Builder().setPublicKey(Key.fromBase64(config.serverKey))
                .setEndpoint(InetEndpoint.parse("${config.endpoint}:${config.port}"))
                .addAllowedIp(InetNetwork.parse("0.0.0.0/0")).setPersistentKeepalive(25).build()
            val engine = backend ?: GoBackend(context).also { backend = it }
            check(engine.setState(tunnel, Tunnel.State.UP, Config.Builder().setInterface(iface).addPeer(peer).build()) == Tunnel.State.UP)
        }
    }
    override suspend fun stop() = withContext(Dispatchers.IO) {
        mutex.withLock {
            stopping = true
            try { backend?.let { check(it.setState(tunnel, Tunnel.State.DOWN, null) == Tunnel.State.DOWN) }; Unit }
            finally { stopping = false }
        }
    }
    override suspend fun verify(config: VpnConfig): Boolean = withContext(Dispatchers.IO) {
        mutex.withLock {
            val engine = backend ?: return@withLock false
            if (engine.getState(tunnel) != Tunnel.State.UP) return@withLock false
            val manager = context.getSystemService(ConnectivityManager::class.java)
            // Link properties must identify THIS tunnel, not merely some other VPN.
            val network = manager.allNetworks.singleOrNull { network ->
                val capabilities = manager.getNetworkCapabilities(network)
                val links = manager.getLinkProperties(network)
                capabilities?.hasTransport(NetworkCapabilities.TRANSPORT_VPN) == true && links != null &&
                    links.linkAddresses.any { it.address.hostAddress == config.address.substringBefore('/') } == true &&
                    links.routes.any { it.isDefaultRoute && it.destination.address is Inet4Address } &&
                    links.dnsServers.mapNotNull { it.hostAddress }.containsAll(config.dns)
            } ?: return@withLock false
            val before = engine.getStatistics(tunnel)
            val peer = before.peer(Key.fromBase64(config.serverKey)) ?: return@withLock false
            val age = System.currentTimeMillis() - peer.latestHandshakeEpochMillis()
            if (peer.latestHandshakeEpochMillis() <= 0 || age !in -5_000..180_000) return@withLock false
            val pool = ConnectionPool(0, 1, TimeUnit.SECONDS)
            val client = OkHttpClient.Builder().socketFactory(network.socketFactory)
                .dns(object : Dns { override fun lookup(hostname: String): List<java.net.InetAddress> = network.getAllByName(hostname).filterIsInstance<Inet4Address>().also { if (it.isEmpty()) throw java.net.UnknownHostException() } })
                .connectionPool(pool).followRedirects(false).followSslRedirects(false).retryOnConnectionFailure(false)
                .connectTimeout(4, TimeUnit.SECONDS).readTimeout(4, TimeUnit.SECONDS).callTimeout(8, TimeUnit.SECONDS).build()
            try {
                // Fixed public canary only; no bearer, cookies, user URL or browsing telemetry.
                val success = client.newCall(Request.Builder().url("https://connectivitycheck.gstatic.com/generate_204")
                    .header("Cache-Control", "no-store").build()).execute().use { it.code == 204 }
                val after = engine.getStatistics(tunnel)
                success && after.totalRx() > before.totalRx() && after.totalTx() > before.totalTx() &&
                    manager.getNetworkCapabilities(network)?.hasTransport(NetworkCapabilities.TRANSPORT_VPN) == true
            } catch (_: Exception) { false } finally { pool.evictAll(); client.dispatcher.executorService.shutdown() }
        }
    }
}
