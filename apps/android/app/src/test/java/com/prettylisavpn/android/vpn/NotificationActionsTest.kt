package com.prettylisavpn.android.vpn

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.runCurrent
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class NotificationActionsTest {
    @Test fun disconnectActionWaitsForAdapterCleanupAndIgnoresUnknownActions() = runTest {
        val removed = CompletableDeferred<Unit>()
        var cleanups = 0
        val adapter = object : ConnectionAdapter {
            override val method = VpnMethod("wireguard", "WireGuard")
            override suspend fun connect(country: String) = ConnectionResult.Verified
            override suspend fun disconnect() { cleanups++; removed.await() }
        }
        val controller = VpnController({ "owner" }, this, listOf(adapter))
        controller.connect("DE"); runCurrent()
        assertEquals(VpnPhase.CONNECTED, controller.status.value.phase)
        assertFalse(dispatchVpnNotificationAction("other", controller))
        assertTrue(dispatchVpnNotificationAction(VPN_DISCONNECT_ACTION, controller))
        runCurrent()
        assertEquals(1, cleanups)
        assertEquals(VpnPhase.DISCONNECTING, controller.status.value.phase)
        dispatchVpnNotificationAction(VPN_DISCONNECT_ACTION, controller)
        assertEquals(1, cleanups)
        removed.complete(Unit); runCurrent()
        assertEquals(VpnPhase.DISCONNECTED, controller.status.value.phase)
    }
}
