package com.prettylisavpn.android.vpn

import com.prettylisavpn.android.auth.SessionCoordinator
import com.prettylisavpn.android.auth.HttpAuthApi
import android.content.Context
import androidx.core.content.edit
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob

class AndroidVpnHost private constructor(context: Context, sessions: SessionCoordinator, http: HttpAuthApi) : VpnActions {
    private val preference = MethodPreference(
        read = { context.getSharedPreferences("vpn-method", Context.MODE_PRIVATE).getString("last-successful-method", null) },
        write = { method -> context.getSharedPreferences("vpn-method", Context.MODE_PRIVATE).edit { putString("last-successful-method", method) } })
    private val wireguard: WireGuardAdapter = WireGuardAdapter(context, sessions, http) { disconnect() }
    private val relay: WireGuardAdapter = WireGuardAdapter(context, sessions, http, viaRelay = true) { disconnect() }
    private val engines = connectionMethods.filter { it.id.removeSuffix("_relay") in managedMethods }
        .map { ManagedAdapter(context, sessions, http, it) { disconnect() } }
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
    val controller: VpnController = VpnController({ sessions.profile?.id }, CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate),
        listOf(wireguard, relay) + engines, preference, recovery = recovery,
        enabledMethods = DeviceMethodSelection.get(context)::current)
    override val status get() = controller.status
    override fun connect(country: String) = controller.connect(country)
    override fun disconnect(): Unit = controller.disconnect()
    fun serviceLost() { if (wireguard.isRunning || relay.isRunning || engines.any { it.isRunning }) disconnect() }
    fun wireguardDiagnostic() = if (relay.isRunning) relay.diagnostic() else wireguard.diagnostic()
    companion object {
        @Volatile private var instance: AndroidVpnHost? = null
        fun current() = instance
        @Synchronized fun create(context: Context, sessions: SessionCoordinator, http: HttpAuthApi): AndroidVpnHost =
            instance ?: AndroidVpnHost(context.applicationContext, sessions, http).also { instance = it }
    }
}
