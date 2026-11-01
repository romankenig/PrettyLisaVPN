package com.prettylisavpn.android.vpn

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.annotation.SuppressLint
import android.net.VpnService
import com.prettylisavpn.android.MainActivity
import com.prettylisavpn.android.R
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.collect

internal const val VPN_NOTIFICATION_ID = 31

internal fun vpnNotification(context: android.content.Context, status: VpnStatus): Notification {
    val open = PendingIntent.getActivity(context, 0, Intent(context, MainActivity::class.java)
        .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
    val disconnect = PendingIntent.getService(context, 1,
        Intent(context, TunnelForegroundService::class.java).setAction(VPN_DISCONNECT_ACTION),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
    val text = context.getString(when (status.phase) {
        VpnPhase.CONNECTED -> R.string.notification_vpn_connected
        VpnPhase.DISCONNECTING -> R.string.notification_vpn_disconnecting
        VpnPhase.FAILED -> R.string.vpn_cleanup
        else -> R.string.notification_vpn_connecting
    })
    return Notification.Builder(context, "vpn").setSmallIcon(R.drawable.brand_mark)
        .setContentTitle("PrettyLisaVPN").setContentText(text)
        .setContentIntent(open).setOngoing(true).setOnlyAlertOnce(true)
        .setCategory(Notification.CATEGORY_SERVICE).setVisibility(Notification.VISIBILITY_PUBLIC)
        .addAction(Notification.Action.Builder(null, context.getString(R.string.notification_open), open).build())
        .apply {
            if (status.phase != VpnPhase.DISCONNECTING)
                addAction(Notification.Action.Builder(null, context.getString(R.string.notification_disconnect), disconnect).build())
        }.build()
}

/** Keeps the single-APK tunnel process alive while the screen is off. */
class TunnelForegroundService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    override fun onBind(intent: Intent?): IBinder? = null
    @SuppressLint("ForegroundServicePermission") // Approved VPN is a documented systemExempted alternative to alarm permissions.
    override fun onCreate() {
        super.onCreate()
        if (VpnService.prepare(this) != null) { stopSelf(); return }
        getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel("vpn", "PrettyLisaVPN", NotificationManager.IMPORTANCE_LOW))
        val host = AndroidVpnHost.current()
        val notification = vpnNotification(this, host?.status?.value ?: VpnStatus(VpnPhase.CONNECTING))
        if (Build.VERSION.SDK_INT >= 34) startForeground(VPN_NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SYSTEM_EXEMPTED)
        else startForeground(VPN_NOTIFICATION_ID, notification)
        if (host != null) scope.launch {
            host.status.combine(com.prettylisavpn.android.ui.PresentationStore.get(this@TunnelForegroundService).preference.language) { status, language -> status to language }
                .collect { (status, language) ->
                    val configuration = android.content.res.Configuration(resources.configuration)
                    configuration.setLocale(java.util.Locale.forLanguageTag(language.code))
                    if (Build.VERSION.SDK_INT < 33 || checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) == android.content.pm.PackageManager.PERMISSION_GRANTED)
                        getSystemService(NotificationManager::class.java).notify(VPN_NOTIFICATION_ID,
                            vpnNotification(createConfigurationContext(configuration), status))
                }
        }
    }
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == VPN_DISCONNECT_ACTION) {
            val host = AndroidVpnHost.current()
            if (!dispatchVpnNotificationAction(intent.action, host)) stopSelf()
        }
        return START_NOT_STICKY
    }
    override fun onDestroy() {
        scope.cancel()
        stopForeground(STOP_FOREGROUND_REMOVE)
        AndroidVpnHost.current()?.serviceLost()
        super.onDestroy()
    }
}
