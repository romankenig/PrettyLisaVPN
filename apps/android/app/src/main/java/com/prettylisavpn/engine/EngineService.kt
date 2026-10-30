package com.prettylisavpn.engine

import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.VpnService
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.ParcelFileDescriptor
import android.os.Process
import com.prettylisavpn.android.R
import com.prettylisavpn.enginecore.mobile.Mobile
import com.prettylisavpn.enginecore.mobile.Platform
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.RejectedExecutionException
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong

/** A private process in the single APK owns one TUN and one permissive native core. */
class EngineService : VpnService() {
    private val worker = Executors.newSingleThreadExecutor()
    private val epoch = AtomicLong()
    private val stopping = AtomicBoolean()
    private val handler = Handler(Looper.getMainLooper())
    private val engine = Mobile.newEngine()
    @Volatile private var tun: ParcelFileDescriptor? = null
    @Volatile private var owner: IBinder? = null
    @Volatile var running = false
        private set
    private val death = IBinder.DeathRecipient { requestStop() }
    private val ownerlessStop = Runnable { if (owner == null) stopSelf() }

    override fun onCreate() { super.onCreate(); instance = this }
    @SuppressLint("ForegroundServicePermission") // Approved VPN is a systemExempted alternative.
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (prepare(this) != null) { stopSelf(); return START_NOT_STICKY }
        getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel("vpn", "PrettyLisaVPN", NotificationManager.IMPORTANCE_LOW))
        val notification = Notification.Builder(this, "vpn").setSmallIcon(R.drawable.ic_launcher)
            .setContentTitle("PrettyLisaVPN").setOngoing(true).build()
        if (Build.VERSION.SDK_INT >= 34) startForeground(32, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SYSTEM_EXEMPTED)
        else startForeground(32, notification)
        handler.postDelayed(ownerlessStop, 60_000)
        return START_NOT_STICKY
    }

    fun startProfile(profile: String, client: IBinder): String {
        val generation = epoch.get()
        return bounded("ENGINE_START_FAILED") {
            if (stopping.get() || generation != epoch.get() || prepare(this) != null) return@bounded "PERMISSION_REQUIRED"
            if (running || owner != null) return@bounded "ENGINE_ALREADY_RUNNING"
            handler.removeCallbacks(ownerlessStop)
            try {
                client.linkToDeath(death, 0); owner = client
                // Protected uplinks follow the system's current physical network.
                // Losing the old Wi-Fi/mobile network is not proof that this VPN failed.
                setUnderlyingNetworks(null)
                engine.start(profile, platform)
                if (generation != epoch.get() || !client.isBinderAlive) { closeOwned(); return@bounded "ENGINE_START_FAILED" }
                running = true
                "RUNNING"
            } catch (_: Exception) { closeOwned(); "ENGINE_START_FAILED" }
        }
    }
    fun stopProfile(): Boolean { epoch.incrementAndGet(); return bounded(false) { closeOwned(); true } }
    fun requestStop() {
        if (!stopping.compareAndSet(false, true)) return
        epoch.incrementAndGet()
        val killer = Runnable { Process.killProcess(Process.myPid()) }
        handler.postDelayed(killer, 5_000)
        try { worker.execute {
            closeOwned()
            handler.removeCallbacks(killer)
            handler.post { stopSelf() }
        } } catch (_: RejectedExecutionException) { Process.killProcess(Process.myPid()) }
    }
    private fun closeOwned() {
        try {
            engine.stop(); tun?.close(); tun = null
            try { owner?.unlinkToDeath(death, 0) } catch (_: NoSuchElementException) { }
            owner = null; running = false
        } catch (_: Exception) {
            Process.killProcess(Process.myPid())
            throw IllegalStateException("ENGINE_STOP_FAILED")
        }
    }
    private fun <T> bounded(failed: T, action: () -> T): T = try {
        worker.submit<T> { action() }.get(30, TimeUnit.SECONDS)
    } catch (_: Exception) { requestStop(); failed }
    private val platform = object : Platform {
        override fun protect(fd: Int): Boolean = this@EngineService.protect(fd)
        override fun openTun(): Int {
            check(tun == null && prepare(this@EngineService) == null)
            return Builder().setSession("PrettyLisaVPN").setMtu(1280)
                .addAddress("172.30.255.1", 30).addAddress("fd7a:115c:a1e0::1", 126)
                .addDnsServer("1.1.1.1").addRoute("0.0.0.0", 0).addRoute("::", 0)
                .establish()?.also { tun = it }?.fd ?: error("TUN_UNAVAILABLE")
        }
    }
    override fun onRevoke() { requestStop() }
    override fun onDestroy() {
        instance = null; handler.removeCallbacks(ownerlessStop)
        requestStop(); worker.shutdown(); super.onDestroy()
    }
    companion object { @Volatile var instance: EngineService? = null; private set }
}
