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
        val controller = VpnController({ "owner" }, backgroundScope, listOf(adapter), recovery = adapter)
        controller.recover()
        runCurrent()
        controller.recover()
        runCurrent()
        assertEquals(1, count)
        assertEquals(VpnPhase.DISCONNECTED, controller.status.value.phase)
    }

    @Test fun startupServerFailureStaysDisconnectedAndFencesNextConnection() = runTest {
        val cleanup = CompletableDeferred<Unit>()
        var connected = false
        val adapter = object : ConnectionAdapter {
            override val method = VpnMethod("wireguard", "WireGuard")
            override suspend fun connect(country: String): ConnectionResult {
                connected = true
                return ConnectionResult.Verified
            }
            override suspend fun disconnect() { cleanup.await() }
            override suspend fun recover() {
                disconnectCleanup({}, { error("offline") })
            }
        }
        val controller = VpnController({ "owner" }, backgroundScope, listOf(adapter), recovery = adapter)
        controller.recover()
        runCurrent()
        assertEquals(VpnStatus(), controller.status.value)
        controller.connect("AUTO")
        runCurrent()
        assertFalse(connected)
        cleanup.complete(Unit)
        runCurrent()
        assertTrue(connected)
    }

    @Test fun localShutdownUpdatesStatusBeforeServerCleanupCompletes() = runTest {
        val remote = CompletableDeferred<Unit>()
        val adapter = object : ConnectionAdapter {
            override val method = VpnMethod("wireguard", "WireGuard")
            override suspend fun connect(country: String) = ConnectionResult.Verified
            override suspend fun disconnect() = disconnect {}
            override suspend fun disconnect(onLocalStopped: () -> Unit) {
                disconnectCleanup({}, { remote.await() }, onLocalStopped)
            }
        }
        val controller = VpnController({ "owner" }, backgroundScope, listOf(adapter))
        controller.connect("AUTO")
        runCurrent()
        controller.disconnect()
        runCurrent()
        assertEquals(VpnStatus(cleanupInProgress = true), controller.status.value)
        remote.completeExceptionally(IllegalStateException("offline"))
        runCurrent()
        assertEquals(VpnStatus(error = VpnError.CLEANUP), controller.status.value)
    }
}
