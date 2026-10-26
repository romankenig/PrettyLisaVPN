package com.prettylisavpn.android.vpn

import com.prettylisavpn.android.auth.SessionCoordinator
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob

class AndroidVpnHost private constructor(sessions: SessionCoordinator) : VpnActions {
    val controller = VpnController({ sessions.profile?.id }, CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate))
    override val status get() = controller.status
    override fun connect(country: String) = controller.connect(country)
    override fun disconnect() = controller.disconnect()
    fun serviceLost() = disconnect()
    companion object {
        @Volatile private var instance: AndroidVpnHost? = null
        @Synchronized fun create(sessions: SessionCoordinator): AndroidVpnHost =
            instance ?: AndroidVpnHost(sessions).also { instance = it }
    }
}
