package com.prettylisavpn.android.diagnostics

import android.content.Context
import android.app.Application
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.os.SystemClock
import java.io.File
import java.time.Instant
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.ThreadPoolExecutor
import java.util.concurrent.TimeUnit

/** Collection is local only. No upload path exists here; support explicitly takes a snapshot. */
class AppDiagnostics private constructor(private val application: Application) {
    private val journal = DiagnosticJournal(File(application.noBackupFilesDir, "support-diagnostics"))
    private val owner = application.getSharedPreferences("diagnostic-owner", Context.MODE_PRIVATE)
    @Volatile private var currentOwner = owner.getString("account", null)
    @Volatile private var ownerReady = true
    private val dropped = java.util.concurrent.atomic.AtomicInteger()
    private val writer = ThreadPoolExecutor(1, 1, 0, TimeUnit.SECONDS, ArrayBlockingQueue(256),
        { task -> Thread(task, "PrettyLisaVPN-diagnostics").apply { isDaemon = true } }, ThreadPoolExecutor.DiscardPolicy())
    private var previousNetwork: NetworkDiagnostic? = null

    init {
        record(DiagnosticKind.APP_START)
        val manager = application.getSystemService(ConnectivityManager::class.java)
        runCatching { manager.registerDefaultNetworkCallback(object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) = networkChanged()
            override fun onLost(network: Network) = networkChanged()
            override fun onCapabilitiesChanged(network: Network, capabilities: NetworkCapabilities) = networkChanged()
        }) }
        val previous = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, error ->
            try { journal.append(DiagnosticEvent(Instant.now().toString(), SystemClock.elapsedRealtime(), DiagnosticKind.APP_ERROR, failure = diagnosticFailure(error), frames = diagnosticFrames(error))) }
            catch (_: Exception) { /* Diagnostic failure must not replace the original crash. */ }
            finally { previous?.uncaughtException(thread, error) }
        }
    }

    @Synchronized private fun networkChanged() {
        val network = networkDiagnostic(application)
        if (network != previousNetwork) { previousNetwork = network; record(DiagnosticKind.NETWORK_CHANGE, network = network) }
    }

    fun record(kind: DiagnosticKind, method: String? = null, phase: String? = null,
        stage: DiagnosticStage? = null, outcome: DiagnosticOutcome? = null,
        failure: DiagnosticFailure? = null, operation: DiagnosticOperation? = null,
        duration: Long? = null, httpStatus: Int? = null, network: NetworkDiagnostic? = null, country: String? = null) {
        val event = DiagnosticEvent(Instant.now().toString(), SystemClock.elapsedRealtime(), kind, method, phase,
            stage, outcome, failure, operation, duration?.coerceAtLeast(0), httpStatus, network, country)
        append(event)
    }

    @Synchronized fun append(event: DiagnosticEvent) {
        if (writer.queue.remainingCapacity() == 0) { dropped.incrementAndGet(); return }
        writer.execute { runCatching { check(ownerReady); journal.append(event) }.onFailure { dropped.incrementAndGet() } }
    }

    /** Account switching cannot attach another account's local diagnostic history. */
    // KTX edit(commit=true) discards the result; do not export until ownership is durable.
    @android.annotation.SuppressLint("UseKtx")
    @Synchronized fun account(id: String?) {
        if (currentOwner == id && ownerReady) return
        currentOwner = id
        ownerReady = false
        dropped.set(0)
        // A full diagnostic queue must never discard the account-isolation barrier.
        writer.queue.clear()
        writer.execute { runCatching {
            journal.clear()
            check(owner.edit().putString("account", id).commit())
            ownerReady = true
        } }
    }

    fun snapshot(): DiagnosticLog {
        val account = currentOwner
        val value = runCatching {
            val pending = synchronized(this) {
                if (writer.queue.remainingCapacity() == 0) null else writer.submit<DiagnosticLog> { check(ownerReady); journal.snapshot() }
            }
            pending?.get(3, TimeUnit.SECONDS) ?: DiagnosticLog(emptyList(), 0, available = false)
        }
            .getOrElse { DiagnosticLog(emptyList(), 0, available = false) }
        return if (account == currentOwner && ownerReady) value.copy(dropped_events = dropped.get()) else DiagnosticLog(emptyList(), 0, available = false)
    }

    companion object {
        @Volatile private var instance: AppDiagnostics? = null
        @Synchronized fun get(context: Context): AppDiagnostics = instance ?: AppDiagnostics(context.applicationContext as Application).also { instance = it }
    }
}

fun networkDiagnostic(context: Context): NetworkDiagnostic = runCatching {
    val manager = context.getSystemService(ConnectivityManager::class.java)
    val capabilities = manager.getNetworkCapabilities(manager.activeNetwork)
    val transports = listOf(NetworkCapabilities.TRANSPORT_WIFI to "WIFI", NetworkCapabilities.TRANSPORT_CELLULAR to "CELLULAR",
        NetworkCapabilities.TRANSPORT_ETHERNET to "ETHERNET", NetworkCapabilities.TRANSPORT_VPN to "VPN")
        .filter { capabilities?.hasTransport(it.first) == true }.map { it.second }
    NetworkDiagnostic(transports.ifEmpty { if (capabilities == null) emptyList() else listOf("OTHER") },
        capabilities?.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) == true,
        capabilities?.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED) == true,
        capabilities?.hasCapability(NetworkCapabilities.NET_CAPABILITY_CAPTIVE_PORTAL) == true, manager.isActiveNetworkMetered)
}.getOrElse { NetworkDiagnostic(emptyList(), false, false, false, null) }
