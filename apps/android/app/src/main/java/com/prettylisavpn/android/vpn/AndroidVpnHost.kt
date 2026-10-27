package com.prettylisavpn.android.vpn

import com.prettylisavpn.android.auth.SessionCoordinator
import com.prettylisavpn.android.auth.HttpAuthApi
import android.content.Context
import com.prettylisavpn.android.vpn.placeholders.placeholderAdapters
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob

class AndroidVpnHost private constructor(context: Context, sessions: SessionCoordinator, http: HttpAuthApi) : VpnActions {
    private val wireguard = WireGuardAdapter(context, sessions, http) { disconnect() }
    val controller = VpnController({ sessions.profile?.id }, CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate),
        placeholderAdapters().map { if (it.method.id == "wireguard") wireguard else it })
    override val status get() = controller.status
    override fun connect(country: String) = controller.connect(country)
    override fun disconnect() = controller.disconnect()
    fun serviceLost() { if (wireguard.isRunning) disconnect() }
    companion object {
        @Volatile private var instance: AndroidVpnHost? = null
        fun current() = instance
        @Synchronized fun create(context: Context, sessions: SessionCoordinator, http: HttpAuthApi): AndroidVpnHost =
            instance ?: AndroidVpnHost(context.applicationContext, sessions, http).also { instance = it }
    }
}
