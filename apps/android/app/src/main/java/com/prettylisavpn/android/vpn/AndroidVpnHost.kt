package com.prettylisavpn.android.vpn

import com.prettylisavpn.android.auth.SessionCoordinator
import com.prettylisavpn.android.auth.HttpAuthApi
import android.content.Context
import androidx.core.content.edit
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.collect

class AndroidVpnHost private constructor(context: Context, private val sessions: SessionCoordinator, http: HttpAuthApi) : VpnActions {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val diagnostics = com.prettylisavpn.android.diagnostics.AppDiagnostics.get(context)
    private val saved = context.getSharedPreferences("vpn-method", Context.MODE_PRIVATE)
    private val preference = MethodPreference(
        read = { saved.getString("last-successful-method", null) },
        write = { method -> saved.edit { putString("last-successful-method", method) } },
        readFailures = { saved.all.entries.filter { it.key.startsWith("failure:") && it.value is Long }.associate { it.key.removePrefix("failure:") to it.value as Long } },
        writeFailures = { failures -> saved.edit { saved.all.keys.filter { it.startsWith("failure:") }.forEach(::remove); failures.forEach { (id, at) -> putLong("failure:$id", at) } } },
        explore = { kotlin.random.Random.nextInt(10) == 0 })
    private val wireguard: WireGuardAdapter = WireGuardAdapter(context, sessions, http, transportLost = { controller.transportLost("wireguard") }) { disconnect() }
    private val relay: WireGuardAdapter = WireGuardAdapter(context, sessions, http, viaRelay = true, transportLost = { controller.transportLost("wireguard_relay") }) { disconnect() }
    private val engines = connectionMethods.filter { it.id.removeSuffix("_relay") in managedMethods }
        .map { method -> ManagedAdapter(context, sessions, http, method, transportLost = { controller.transportLost(method.id) }) { disconnect() } }
    private val recovery = object : ConnectionAdapter {
        override val method = wireguard.method
        override suspend fun connect(country: String) = ConnectionResult.Failed
        override suspend fun disconnect() = recover()
        override suspend fun recover() {
            // A surviving private engine process must close before restoring the
            // control route and recovering this device's common remote lease.
            ManagedRuntime(context) {}.stop()
            wireguard.recover()
        }
    }
    val controller: VpnController = VpnController({ sessions.profile?.id }, scope,
        listOf(wireguard, relay) + engines, preference, recovery = recovery,
        enabledMethods = { DeviceMethodSelection.get(context).current() }, healthPolicy = ConnectionHealthPolicy(),
        elapsedMillis = android.os.SystemClock::elapsedRealtime,
        diagnostics = diagnostics::append)
    init {
        scope.launch { controller.status.collect { state ->
            diagnostics.record(
                com.prettylisavpn.android.diagnostics.DiagnosticKind.VPN_STATE,
                method = (state.method ?: state.attempt?.method)?.id, phase = state.phase.name,
                failure = state.error?.let { com.prettylisavpn.android.diagnostics.DiagnosticFailure.valueOf(it.name) })
            if (state.phase == VpnPhase.DISCONNECTED || (state.phase == VpnPhase.FAILED && state.error != VpnError.CLEANUP))
                context.stopService(android.content.Intent(context, TunnelForegroundService::class.java))
        } }
    }
    override val status get() = controller.status
    override fun connect(country: String) = controller.connect(if (sessions.profile?.isDemo == true) "AUTO" else country)
    override fun disconnect(): Unit = controller.disconnect()
    override fun resetMethods(country: String) = controller.resetMethods(if (sessions.profile?.isDemo == true) "AUTO" else country)
    fun serviceLost() { if (wireguard.isRunning || relay.isRunning || engines.any { it.isRunning }) {
        diagnostics.record(com.prettylisavpn.android.diagnostics.DiagnosticKind.VPN_SERVICE_LOST)
        disconnect()
    } }
    fun wireguardDiagnostic() = if (relay.isRunning) relay.diagnostic() else wireguard.diagnostic()
    internal fun managedDiagnostic(method: String) = engines.firstOrNull { it.method.id == method }?.diagnostic()
    companion object {
        @Volatile private var instance: AndroidVpnHost? = null
        fun current() = instance
        @Synchronized fun create(context: Context, sessions: SessionCoordinator, http: HttpAuthApi): AndroidVpnHost =
            instance ?: AndroidVpnHost(context.applicationContext, sessions, http).also { instance = it }
    }
}
