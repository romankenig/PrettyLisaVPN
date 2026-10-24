package com.prettylisavpn.engine

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.VpnService
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.ParcelFileDescriptor
import android.os.Process
import com.prettylisavpn.enginecore.mobile.Mobile
import com.prettylisavpn.enginecore.mobile.Platform
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicLong
import okhttp3.ConnectionPool
import okhttp3.Dns
import okhttp3.OkHttpClient
import okhttp3.Request

/** Owns the one TUN and the one Go runtime in this separately installed process. */
class EngineService : VpnService() {
    // Closed results are safe to show without USB; never include exception text.
    private enum class Verification {
        VERIFIED, NOT_RUNNING, VPN_NETWORK_MISSING, VPN_OWNER_MISMATCH,
        VPN_ROUTE_MISMATCH, DNS_FAILED, HTTPS_FAILED, HTTPS_REJECTED,
        STATE_CHANGED, VERIFY_TIMEOUT, UPLINK_PROTECTION_FAILED,
    }
    @Volatile private var protectionFailed = false
    private val worker = Executors.newSingleThreadExecutor()
    private val epoch = AtomicLong()
    private val handler = Handler(Looper.getMainLooper())
    private val engine = Mobile.newEngine()
    @Volatile private var tun: ParcelFileDescriptor? = null
    @Volatile private var owner: IBinder? = null
    @Volatile private var underlying: Network? = null
    @Volatile var running = false
        private set
    private val death = IBinder.DeathRecipient { requestStop() }
    private val networks by lazy { getSystemService(ConnectivityManager::class.java) }
    private val networkCallback = object : ConnectivityManager.NetworkCallback() {
        override fun onLost(network: Network) { if (network == underlying) requestStop() }
    }
    override fun onCreate() {
        super.onCreate()
        instance = this
        networks.registerNetworkCallback(android.net.NetworkRequest.Builder().addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET).addCapability(NetworkCapabilities.NET_CAPABILITY_NOT_VPN).build(), networkCallback)
    }
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (prepare(this) != null) { stopSelf(); return START_NOT_STICKY }
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel("engine", "PrettyLisaVPN", NotificationManager.IMPORTANCE_LOW))
        val notification = Notification.Builder(this, "engine")
            .setSmallIcon(android.R.drawable.ic_lock_lock).setContentTitle("PrettyLisaVPN")
            .setOngoing(true).setCategory(Notification.CATEGORY_SERVICE).build()
        try {
            if (Build.VERSION.SDK_INT >= 34) startForeground(42, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SYSTEM_EXEMPTED)
            else startForeground(42, notification)
        } catch (_: Exception) { stopSelf() }
        handler.postDelayed({ if (owner == null && !running) stopSelf() }, 60_000)
        return START_NOT_STICKY
    }
    fun startProfile(profile: String, client: IBinder): String {
        val generation = epoch.get()
        return bounded("ENGINE_START_FAILED") {
            if (generation != epoch.get() || prepare(this) != null) return@bounded "PERMISSION_REQUIRED"
            if (running || owner != null) return@bounded "ENGINE_ALREADY_RUNNING"
            protectionFailed = false
            try {
                client.linkToDeath(death, 0)
                owner = client
                underlying = networks.allNetworks.firstOrNull { network -> networks.getNetworkCapabilities(network)?.let {
                    it.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) && it.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_VPN) && it.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
                } == true } ?: throw IllegalStateException()
                setUnderlyingNetworks(arrayOf(underlying!!))
                engine.start(profile, platform)
                if (generation != epoch.get() || !client.isBinderAlive) { closeOwned(); return@bounded "ENGINE_START_FAILED" }
                running = true
                "RUNNING"
            } catch (_: Exception) { closeOwned(); "ENGINE_START_FAILED" }
        }
    }
    fun stopProfile(): Boolean { epoch.incrementAndGet(); return bounded(false) { closeOwned(); true } }
    fun requestStop() {
        epoch.incrementAndGet()
        // A stuck native operation must not leave traffic alive after parent death.
        val killer = Runnable { Process.killProcess(Process.myPid()) }
        handler.postDelayed(killer, 5_000)
        worker.execute {
            closeOwned()
            handler.removeCallbacks(killer)
            handler.post { stopSelf() }
        }
    }
    private fun closeOwned() {
        try {
            engine.stop()
            tun?.close(); tun = null
            try { owner?.unlinkToDeath(death, 0) } catch (_: NoSuchElementException) { /* Already dead. */ }
            owner = null; underlying = null; running = false
        } catch (_: Exception) {
            Process.killProcess(Process.myPid())
            throw IllegalStateException("ENGINE_STOP_FAILED")
        }
    }
    fun verifyInternet(): String = bounded(Verification.VERIFY_TIMEOUT) {
        if (!running || tun == null || prepare(this) != null || owner?.isBinderAlive != true) return@bounded Verification.NOT_RUNNING
        val generation = epoch.get()
        val network = networks.allNetworks.singleOrNull { candidate ->
            val caps = networks.getNetworkCapabilities(candidate)
            val links = networks.getLinkProperties(candidate)
            caps?.hasTransport(NetworkCapabilities.TRANSPORT_VPN) == true &&
                (Build.VERSION.SDK_INT < 30 || caps.ownerUid == Process.myUid()) &&
                links != null && links.linkAddresses.any { it.address.hostAddress == "172.30.255.1" } &&
                links.routes.any { it.isDefaultRoute && it.destination.address is java.net.Inet4Address } &&
                links.dnsServers.any { it.hostAddress == "1.1.1.1" }
        } ?: run {
            val vpn = networks.allNetworks.mapNotNull { networks.getNetworkCapabilities(it) }
                .filter { it.hasTransport(NetworkCapabilities.TRANSPORT_VPN) }
            return@bounded when {
                vpn.isEmpty() -> Verification.VPN_NETWORK_MISSING
                Build.VERSION.SDK_INT >= 30 && vpn.none { it.ownerUid == Process.myUid() } -> Verification.VPN_OWNER_MISMATCH
                else -> Verification.VPN_ROUTE_MISMATCH
            }
        }
        // Both resolution and HTTPS are bound to THIS VPN. Never protect this socket.
        // A fixed public canary carries no account credentials or user browsing data.
        val pool = ConnectionPool(0, 1, TimeUnit.SECONDS)
        var dnsSucceeded = false
        val client = OkHttpClient.Builder().socketFactory(network.socketFactory)
            .dns(object : Dns { override fun lookup(hostname: String): List<java.net.InetAddress> =
                network.getAllByName(hostname).filterIsInstance<java.net.Inet4Address>().also {
                    if (it.isEmpty()) throw java.net.UnknownHostException()
                    dnsSucceeded = true
                } })
            .proxy(java.net.Proxy.NO_PROXY).connectionPool(pool)
            .followRedirects(false).followSslRedirects(false).retryOnConnectionFailure(false)
            .connectTimeout(4, TimeUnit.SECONDS).readTimeout(4, TimeUnit.SECONDS)
            .callTimeout(8, TimeUnit.SECONDS).build()
        try {
            val success = client.newCall(Request.Builder()
                .url("https://connectivitycheck.gstatic.com/generate_204")
                .header("Cache-Control", "no-store").build()).execute().use { it.code == 204 }
            when {
                !success -> Verification.HTTPS_REJECTED
                generation != epoch.get() || !running || tun == null || prepare(this) != null ||
                    networks.getNetworkCapabilities(network)?.hasTransport(NetworkCapabilities.TRANSPORT_VPN) != true -> Verification.STATE_CHANGED
                else -> Verification.VERIFIED
            }
        } catch (_: Exception) {
            when {
                protectionFailed -> Verification.UPLINK_PROTECTION_FAILED
                !dnsSucceeded -> Verification.DNS_FAILED
                else -> Verification.HTTPS_FAILED
            }
        } finally { pool.evictAll(); client.dispatcher.executorService.shutdown() }
    }.name
    private fun <T> bounded(failed: T, action: () -> T): T = try {
        worker.submit<T> { action() }.get(30, TimeUnit.SECONDS)
    } catch (_: Exception) { requestStop(); failed }
    private val platform = object : Platform {
        override fun protect(fd: Int): Boolean = this@EngineService.protect(fd).also {
            if (!it) protectionFailed = true
        }
        override fun openTun(): Int {
            if (tun != null || prepare(this@EngineService) != null) throw IllegalStateException("TUN_UNAVAILABLE")
            return Builder().setSession("PrettyLisaVPN").setMtu(1280)
                .addAddress("172.30.255.1", 30).addAddress("fd7a:115c:a1e0::1", 126)
                .addDnsServer("1.1.1.1").addRoute("0.0.0.0", 0).addRoute("::", 0)
                .establish()?.also { tun = it }?.fd ?: throw IllegalStateException("TUN_UNAVAILABLE")
        }
    }
    override fun onRevoke() { requestStop(); stopSelf() }
    override fun onDestroy() {
        instance = null
        networks.unregisterNetworkCallback(networkCallback)
        requestStop()
        worker.shutdown()
        super.onDestroy()
    }
    companion object {
        @Volatile var instance: EngineService? = null
            private set
    }
}
