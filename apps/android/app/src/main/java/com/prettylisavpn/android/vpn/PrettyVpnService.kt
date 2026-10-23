package com.prettylisavpn.android.vpn

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import com.prettylisavpn.android.MainActivity
import com.prettylisavpn.android.R
import com.wireguard.android.backend.GoBackend
import kotlinx.coroutines.*

/** The ONE TUN owner. super.onCreate registers this instance with GoBackend before start.
 * Removing the library's base service from the manifest is intentional and tested.
 */
class PrettyVpnService : GoBackend.VpnService() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var observer: Job? = null
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        super.onStartCommand(intent, flags, startId)
        val host = AndroidVpnHost.instance
        if (host == null || intent == null || intent.action !in setOf(CONNECT, DISCONNECT)) { stopSelf(); return START_NOT_STICKY }
        if (intent.action == DISCONNECT) { host.disconnect(); return START_NOT_STICKY }
        if (android.net.VpnService.prepare(this) != null) { host.controller.rejected(VpnError.PERMISSION); stopSelf(); return START_NOT_STICKY }
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel(CHANNEL, "PrettyLisaVPN", NotificationManager.IMPORTANCE_LOW))
        val initial = notification(VpnStatus(VpnPhase.CONNECTING))
        try {
            if (Build.VERSION.SDK_INT >= 34) startForeground(ID, initial, ServiceInfo.FOREGROUND_SERVICE_TYPE_SYSTEM_EXEMPTED)
            else startForeground(ID, initial)
        } catch (_: Exception) { host.controller.rejected(VpnError.PERMISSION); stopSelf(); return START_NOT_STICKY }
        host.controller.connect(intent.getStringExtra("country") ?: "AUTO")
        observer?.cancel()
        observer = scope.launch { host.status.collect { manager.notify(ID, notification(it)) } }
        return START_NOT_STICKY
    }
    private fun notification(status: VpnStatus): Notification {
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val stop = PendingIntent.getService(this, 1, Intent(this, PrettyVpnService::class.java).setAction(DISCONNECT), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val text = getString(when (status.phase) {
            VpnPhase.CONNECTED -> R.string.vpn_connected
            VpnPhase.VERIFYING -> R.string.vpn_verifying
            VpnPhase.DISCONNECTING, VpnPhase.CLEANUP_PENDING -> R.string.vpn_disconnecting
            else -> R.string.vpn_connecting
        })
        return Notification.Builder(this, CHANNEL).setSmallIcon(R.drawable.ic_vpn_notification)
            .setContentTitle("PrettyLisaVPN").setContentText(text).setContentIntent(open).setOngoing(true)
            .setCategory(Notification.CATEGORY_SERVICE).setOnlyAlertOnce(true)
            .addAction(Notification.Action.Builder(null, getString(R.string.vpn_disconnect), stop).build()).build()
    }
    override fun onRevoke() {
        // Serialize GoBackend DOWN before stopSelf/onDestroy; super would stop the service
        // immediately while a start/statistics JNI call may still be in flight.
        AndroidVpnHost.instance?.serviceLost() ?: stopSelf()
    }
    override fun onDestroy() {
        scope.cancel()
        super.onDestroy() // Native handle/routes are closed even if cleanup cannot reach backend.
        AndroidVpnHost.instance?.serviceLost()
    }
    companion object {
        const val CONNECT = "com.prettylisavpn.android.vpn.CONNECT"
        const val DISCONNECT = "com.prettylisavpn.android.vpn.DISCONNECT"
        private const val CHANNEL = "vpn"
        private const val ID = 41
    }
}
