package com.prettylisavpn.android.vpn

import android.content.Context
import android.content.Intent
import android.net.VpnService
import com.prettylisavpn.android.auth.HttpAuthApi
import com.prettylisavpn.android.auth.SessionCoordinator
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob

/** The service and Activity use the same process-wide coordinator and auth rotation owner. */
class AndroidVpnHost private constructor(context: Context, sessions: SessionCoordinator, api: VpnApi, journal: VpnJournal) : VpnActions {
    private val app = context.applicationContext
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    val controller: VpnController
    init {
        val runtime = WireGuardRuntime(app) { serviceLost() }
        controller = VpnController(api, runtime, journal, { sessions.profile?.id },
            { WireGuardKey() }, scope, { android.os.SystemClock.elapsedRealtime() },
            { app.stopService(Intent(app, PrettyVpnService::class.java)) })
    }
    override val status get() = controller.status
    override fun connect(country: String) {
        try {
            if (VpnService.prepare(app) != null) { controller.rejected(VpnError.PERMISSION); return }
            app.startForegroundService(Intent(app, PrettyVpnService::class.java).setAction(PrettyVpnService.CONNECT).putExtra("country", country))
        } catch (_: Exception) { controller.rejected(VpnError.UNKNOWN) }
    }
    override fun disconnect() { controller.disconnect() }
    fun serviceLost() {
        if (status.value.phase in setOf(VpnPhase.RECONCILING, VpnPhase.CONNECTED, VpnPhase.CONNECTING, VpnPhase.VERIFYING)) controller.disconnect()
    }
    companion object {
        @Volatile var instance: AndroidVpnHost? = null
            private set
        @Synchronized fun create(context: Context, sessions: SessionCoordinator, http: HttpAuthApi,
            api: VpnApi = HttpVpnApi(http, sessions), journal: VpnJournal = EncryptedVpnJournal(context)): AndroidVpnHost =
            instance ?: AndroidVpnHost(context, sessions, api, journal).also { instance = it }
    }
}
