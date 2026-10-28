package com.prettylisavpn.android.vpn

import com.prettylisavpn.android.auth.SessionCoordinator
import com.prettylisavpn.android.auth.HttpAuthApi
import android.content.Context
import androidx.core.content.edit
import com.prettylisavpn.android.vpn.placeholders.placeholderAdapters
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob

class AndroidVpnHost private constructor(context: Context, sessions: SessionCoordinator, http: HttpAuthApi) : VpnActions {
    private val preference = MethodPreference(
        read = { context.getSharedPreferences("vpn-method", Context.MODE_PRIVATE).getString("last-successful-method", null) },
        write = { method -> context.getSharedPreferences("vpn-method", Context.MODE_PRIVATE).edit { putString("last-successful-method", method) } })
    private val wireguard: WireGuardAdapter = WireGuardAdapter(context, sessions, http) { disconnect() }
    private val relay: WireGuardAdapter = WireGuardAdapter(context, sessions, http, viaRelay = true) { disconnect() }
    val controller: VpnController = VpnController({ sessions.profile?.id }, CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate),
        listOf(wireguard, relay) + placeholderAdapters().filter { it.method.id != "wireguard" }, preference)
    override val status get() = controller.status
    override fun connect(country: String) = controller.connect(country)
    override fun disconnect(): Unit = controller.disconnect()
    fun serviceLost() { if (wireguard.isRunning || relay.isRunning) disconnect() }
    fun wireguardDiagnostic() = if (relay.isRunning) relay.diagnostic() else wireguard.diagnostic()
    companion object {
        @Volatile private var instance: AndroidVpnHost? = null
        fun current() = instance
        @Synchronized fun create(context: Context, sessions: SessionCoordinator, http: HttpAuthApi): AndroidVpnHost =
            instance ?: AndroidVpnHost(context.applicationContext, sessions, http).also { instance = it }
    }
}
