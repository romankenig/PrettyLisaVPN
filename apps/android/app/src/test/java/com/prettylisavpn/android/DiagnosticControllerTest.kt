package com.prettylisavpn.android

import com.prettylisavpn.android.diagnostics.*
import com.prettylisavpn.android.vpn.*
import kotlinx.coroutines.delay
import kotlinx.coroutines.test.*
import org.junit.Assert.*
import org.junit.Test

@OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
class DiagnosticControllerTest {
    @Test fun fallbackTimelineAndDiagnosticFailureDoNotChangeVpnBehavior() = runTest {
        var cleanups = 0
        fun adapter(id: String, result: ConnectionResult) = object : ConnectionAdapter {
            override val method = VpnMethod(id, id)
            override suspend fun connect(country: String): ConnectionResult { delay(50); return result }
            override suspend fun disconnect() { cleanups++ }
        }
        val events = mutableListOf<DiagnosticEvent>()
        val controller = VpnController({ "synthetic" }, this,
            listOf(adapter("wireguard", ConnectionResult.Failed), adapter("wireguard_relay", ConnectionResult.Verified)),
            elapsedMillis = { testScheduler.currentTime }, diagnostics = { events.add(it); throw IllegalStateException("disk unavailable") })
        controller.connect("AUTO"); advanceUntilIdle()
        assertEquals(VpnPhase.CONNECTED, controller.status.value.phase)
        val results = events.filter { it.event == DiagnosticKind.VPN_RESULT }
        assertEquals(listOf(DiagnosticOutcome.FAILED, DiagnosticOutcome.SUCCESS), results.map { it.outcome })
        assertEquals(listOf(50L,50L), results.map { it.duration_ms })
        controller.disconnect(); advanceUntilIdle()
        assertEquals(VpnPhase.DISCONNECTED, controller.status.value.phase)
        assertEquals(2, cleanups)
    }
}
