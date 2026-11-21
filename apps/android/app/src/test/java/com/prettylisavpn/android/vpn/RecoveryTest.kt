package com.prettylisavpn.android.vpn

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class RecoveryTest {
    @Test fun startupRecoveryRunsOnce() = runTest {
        var count = 0
        val adapter = object : ConnectionAdapter {
            override val method = VpnMethod("wireguard", "WireGuard")
            override suspend fun connect(country: String) = ConnectionResult.Verified
            override suspend fun disconnect() {}
            override suspend fun recover() { count++ }
        }
        val controller = VpnController({ "owner" }, this, listOf(adapter), recovery = adapter)
        controller.recover(); controller.recover()
        runCurrent()
        controller.recover()
        assertEquals(1, count)
        assertEquals(VpnPhase.DISCONNECTED, controller.status.value.phase)
    }

    @Test fun firstConnectWaitsForStartupCleanupWithoutShowingAnActiveTunnel() = runTest {
        val started = CompletableDeferred<Unit>()
        val finish = CompletableDeferred<Unit>()
        var attempts = 0
        val adapter = object : ConnectionAdapter {
            override val method = VpnMethod("wireguard", "WireGuard")
            override suspend fun recover() { started.complete(Unit); finish.await() }
            override suspend fun connect(country: String): ConnectionResult { attempts++; return ConnectionResult.Verified }
            override suspend fun disconnect() {}
        }
        val controller = VpnController({ "owner" }, backgroundScope, listOf(adapter), recovery = adapter)
        controller.recover()
        runCurrent()
        assertTrue(started.isCompleted)
        assertEquals(VpnPhase.DISCONNECTED, controller.status.value.phase)
        controller.connect("AUTO")
        runCurrent()
        assertEquals(VpnPhase.CONNECTING, controller.status.value.phase)
        assertEquals(0, attempts)
        finish.complete(Unit)
        runCurrent()
        assertEquals(VpnPhase.CONNECTED, controller.status.value.phase)
        assertEquals(1, attempts)
    }

    @Test fun failedStartupCleanupKeepsConnectAvailableAndIsRetriedBeforeAdmission() = runTest {
        val events = mutableListOf<String>()
        var available = false
        val adapter = object : ConnectionAdapter {
            override val method = VpnMethod("wireguard", "WireGuard")
            override suspend fun recover() { events += "cleanup"; check(available) }
            override suspend fun connect(country: String): ConnectionResult { events += "connect"; return ConnectionResult.Verified }
            override suspend fun disconnect() {}
        }
        val controller = VpnController({ "owner" }, backgroundScope, listOf(adapter), recovery = adapter)
        controller.recover()
        runCurrent()
        assertEquals(VpnStatus(), controller.status.value)
        controller.connect("AUTO")
        runCurrent()
        assertEquals(VpnStatus(error = VpnError.CLEANUP), controller.status.value)
        available = true
        controller.connect("AUTO")
        runCurrent()
        assertEquals(listOf("cleanup", "cleanup", "cleanup", "connect"), events)
        assertEquals(VpnPhase.CONNECTED, controller.status.value.phase)
    }
}
