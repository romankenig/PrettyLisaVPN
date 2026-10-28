package com.prettylisavpn.android.vpn

import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test

class RecoveryTest {
    @Test fun startupRecoveryRunsOnce() = runBlocking {
        var count = 0
        val adapter = object : ConnectionAdapter {
            override val method = VpnMethod("wireguard", "WireGuard")
            override suspend fun connect(country: String) = ConnectionResult.Verified
            override suspend fun disconnect() {}
            override suspend fun recover() { count++ }
        }
        val controller = VpnController({ "owner" }, this, listOf(adapter), recovery = adapter)
        controller.recover(); controller.recover()
        assertEquals(1, count)
        assertEquals(VpnPhase.DISCONNECTED, controller.status.value.phase)
    }
}
