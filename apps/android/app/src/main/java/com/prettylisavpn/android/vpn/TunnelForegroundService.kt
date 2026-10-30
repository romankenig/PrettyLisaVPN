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

/** Keeps the single-APK tunnel process alive while the screen is off. */
class TunnelForegroundService : Service() {
    override fun onBind(intent: Intent?): IBinder? = null
    @SuppressLint("ForegroundServicePermission") // Approved VPN is a documented systemExempted alternative to alarm permissions.
    override fun onCreate() {
        super.onCreate()
        if (VpnService.prepare(this) != null) { stopSelf(); return }
        getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel("vpn", "PrettyLisaVPN", NotificationManager.IMPORTANCE_LOW))
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val notification = Notification.Builder(this, "vpn").setSmallIcon(R.drawable.ic_launcher)
            .setContentTitle("PrettyLisaVPN")
            .setContentIntent(open).setOngoing(true).build()
        if (Build.VERSION.SDK_INT >= 34) startForeground(31, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SYSTEM_EXEMPTED)
        else startForeground(31, notification)
    }
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_NOT_STICKY
    override fun onDestroy() { AndroidVpnHost.current()?.serviceLost(); super.onDestroy() }
}
