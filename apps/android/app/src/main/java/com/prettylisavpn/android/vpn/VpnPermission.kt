package com.prettylisavpn.android.vpn

import android.content.Context
import android.content.Intent
import android.net.VpnService
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/** Only an attached foreground Activity may display Android's system VPN consent. */
object VpnPermission {
    var launch: (suspend (Intent) -> Boolean)? = null
    var launchNotifications: (suspend () -> Unit)? = null
    suspend fun request(context: Context): Boolean = withContext(Dispatchers.Main.immediate) {
        val intent = VpnService.prepare(context)
        val approved = intent == null || launch?.invoke(intent) == true
        if (approved) launchNotifications?.invoke()
        approved
    }
}
