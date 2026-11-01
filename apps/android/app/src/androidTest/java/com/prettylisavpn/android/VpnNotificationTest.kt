package com.prettylisavpn.android

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.By
import androidx.test.uiautomator.Until
import com.prettylisavpn.android.vpn.*
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class VpnNotificationTest {
    @Test fun ongoingNoticeHasOpenAndDisconnectActionsAndUpdatesUntilRemoval() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        if (Build.VERSION.SDK_INT >= 33) instrumentation.uiAutomation.grantRuntimePermission(context.packageName, android.Manifest.permission.POST_NOTIFICATIONS)
        if (Build.VERSION.SDK_INT >= 33 && context.checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) != android.content.pm.PackageManager.PERMISSION_GRANTED)
            throw IllegalStateException("Notification permission was not granted to the test APK")
        val manager = context.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel("vpn", "PrettyLisaVPN", NotificationManager.IMPORTANCE_LOW))
        val connected = vpnNotification(context, VpnStatus(VpnPhase.CONNECTED, method = VpnMethod("wireguard", "WireGuard")))
        assertEquals(context.getString(R.string.notification_vpn_connected), connected.extras.getString(Notification.EXTRA_TEXT))
        assertTrue(connected.flags and Notification.FLAG_ONGOING_EVENT != 0)
        assertEquals(2, connected.actions.size)
        assertEquals(context.getString(R.string.notification_open), connected.actions[0].title)
        assertEquals(context.getString(R.string.notification_disconnect), connected.actions[1].title)
        assertNotNull(connected.contentIntent)
        if (Build.VERSION.SDK_INT >= 31) {
            assertTrue(connected.actions[0].actionIntent.isActivity)
            assertTrue(connected.actions[1].actionIntent.isService)
            assertTrue(connected.actions.all { it.actionIntent.isImmutable })
        }
        try {
            manager.notify(VPN_NOTIFICATION_ID, connected)
            val device = UiDevice.getInstance(instrumentation)
            device.openNotification()
            assertTrue(device.wait(Until.hasObject(By.text(context.getString(R.string.notification_vpn_connected))), 5_000))
            assertEquals(1, manager.activeNotifications.count { it.id == VPN_NOTIFICATION_ID })
            val folder = java.io.File(context.getExternalFilesDir(null), "acceptance")
            check(folder.mkdirs() || folder.isDirectory)
            assertTrue(device.takeScreenshot(java.io.File(folder, "vpn-notification.png")))
            val stopping = vpnNotification(context, VpnStatus(VpnPhase.DISCONNECTING))
            assertEquals(1, stopping.actions.size)
            manager.notify(VPN_NOTIFICATION_ID, stopping)
            assertTrue(device.wait(Until.hasObject(By.text(context.getString(R.string.notification_vpn_disconnecting))), 5_000))
            assertEquals(context.getString(R.string.notification_vpn_disconnecting), manager.activeNotifications.first { it.id == VPN_NOTIFICATION_ID }.notification.extras.getString(Notification.EXTRA_TEXT))
        } finally { manager.cancel(VPN_NOTIFICATION_ID); UiDevice.getInstance(instrumentation).pressBack() }
        assertTrue(manager.activeNotifications.none { it.id == VPN_NOTIFICATION_ID })
    }
}
