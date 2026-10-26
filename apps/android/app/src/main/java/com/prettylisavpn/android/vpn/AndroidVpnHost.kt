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
class AndroidVpnHost private constructor(context: Context, sessions: SessionCoordinator, http: HttpAuthApi, api: VpnApi?, journal: VpnJournal) : VpnActions {
    private val app = context.applicationContext as android.app.Application
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val managed = ManagedTunnelClient(app) { serviceLost() }
    val controller: VpnController
    init {
        controller = VpnController(api ?: HttpVpnApi(http, sessions, true), managed, journal, { sessions.profile?.id },
            { WireGuardKey() }, scope, { android.os.SystemClock.elapsedRealtime() },
            { managed.release() })
    }
    override val status get() = controller.status
    override fun connect(country: String) {
        try {
            if (country != "AUTO" && !country.matches(Regex("[A-Z]{2}"))) { controller.rejected(VpnError.UNSUPPORTED); return }
            if (!permissionReady(app)) { controller.rejected(VpnError.PERMISSION); return }
            controller.connect(country)
        } catch (_: Exception) { controller.rejected(VpnError.UNKNOWN) }
    }
    override fun disconnect() { controller.disconnect() }
    override fun permissionIntent(context: Context): Intent = managed.consentIntent()
    override fun permissionResult(accepted: Boolean) { managed.consentResult(accepted) }
    override fun permissionReady(context: Context): Boolean = managed.consented && VpnService.prepare(context) == null
    override val ownsNotifications: Boolean get() = true
    fun serviceLost() {
        if (status.value.phase in setOf(VpnPhase.RECONCILING, VpnPhase.CONNECTED, VpnPhase.CONNECTING, VpnPhase.VERIFYING)) controller.disconnect()
    }
    companion object {
        @Volatile var instance: AndroidVpnHost? = null
            private set
        @Synchronized fun create(context: Context, sessions: SessionCoordinator, http: HttpAuthApi,
            api: VpnApi? = null, journal: VpnJournal = EncryptedVpnJournal(context)): AndroidVpnHost =
            instance ?: AndroidVpnHost(context, sessions, http, api, journal).also { instance = it }
    }
}
