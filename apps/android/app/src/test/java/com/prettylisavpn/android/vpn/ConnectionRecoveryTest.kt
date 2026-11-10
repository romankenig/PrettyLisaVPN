package com.prettylisavpn.android.vpn

import kotlinx.coroutines.*
import kotlinx.coroutines.test.*
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class ConnectionRecoveryTest {
    @Test fun freeQuotaStopsRetriesAndKeepsSupportVocabularyCompatible() = runTest {
        for (code in listOf("FREE_QUOTA_EXHAUSTED", "FREE_DAILY_LIMIT_REACHED", "FREE_QUOTA_RESERVED")) {
            val events = mutableListOf<String>()
            val denied = object : ConnectionAdapter {
                override val method = VpnMethod("wireguard", "WireGuard")
                override suspend fun connect(country: String): ConnectionResult { events += "start"; throw com.prettylisavpn.android.auth.AuthFailure(code) }
                override suspend fun disconnect() { events += "cleanup" }
            }
            val controller = VpnController({ "owner" }, backgroundScope, listOf(denied, Adapter("vless", events)))
            controller.connect("AUTO"); runCurrent()
            assertEquals(listOf("start", "cleanup"), events)
            assertEquals(if (code == "FREE_QUOTA_RESERVED") VpnError.ACCESS else VpnError.FREE_LIMIT, controller.status.value.error)
            assertEquals("ACCESS", supportFailureCode(controller.status.value.error))
        }
    }
    @Test fun demoQuotaStopsMethodExplorationAfterCleanup() = runTest {
        val events = mutableListOf<String>()
        val exhausted = object : ConnectionAdapter {
            override val method = VpnMethod("wireguard", "WireGuard")
            override suspend fun connect(country: String): ConnectionResult {
                events += "start"
                throw com.prettylisavpn.android.auth.AuthFailure("DEMO_QUOTA_EXHAUSTED")
            }
            override suspend fun disconnect() { events += "cleanup" }
        }
        val next = Adapter("vless", events)
        val controller = VpnController({ "guest" }, backgroundScope, listOf(exhausted, next))
        controller.connect("AUTO"); runCurrent()
        assertEquals(listOf("start", "cleanup"), events)
        assertEquals(VpnError.DEMO_LIMIT, controller.status.value.error)
    }
    private val policy = ConnectionHealthPolicy(intervalMillis = 30, retryMillis = 5, recoveryBackoffMillis = 3, recoveryWindowMillis = 10_000)
    private class Adapter(id: String, private val events: MutableList<String>) : ConnectionAdapter {
        override val method = VpnMethod(id, id)
        var result = TunnelHealth.HEALTHY
        var cleanupGate: CompletableDeferred<Unit>? = null
        var probeGate: CompletableDeferred<Unit>? = null
        var cleanupFails = false
        override suspend fun connect(country: String): ConnectionResult { events += "start:${method.id}:$country"; return ConnectionResult.Verified }
        override suspend fun disconnect() { cleanupGate?.await(); if (cleanupFails) error("cleanup"); events += "stop:${method.id}" }
        override suspend fun health(): TunnelHealth { probeGate?.await(); events += "probe:${method.id}"; return result }
    }
    @Test fun delayedFailureIsConfirmedAndCleanupPrecedesAlternateMethod() = runTest {
        val events = mutableListOf<String>()
        val first = Adapter("wireguard_relay", events)
        val next = Adapter("vless", events)
        val preference = MethodPreference(read = { "wireguard_relay" }, now = { testScheduler.currentTime })
        val controller = VpnController({ "owner" }, backgroundScope, listOf(first, next), preference, healthPolicy = policy, elapsedMillis = { testScheduler.currentTime })
        controller.connect("NL"); runCurrent()
        first.result = TunnelHealth.UNREACHABLE
        advanceTimeBy(30); runCurrent()
        assertEquals(VpnPhase.CHECKING, controller.status.value.phase)
        assertFalse(events.contains("stop:wireguard_relay"))
        advanceTimeBy(10); runCurrent()
        assertEquals(VpnPhase.RECONNECTING, controller.status.value.phase)
        advanceTimeBy(3); runCurrent()
        assertEquals("vless", controller.status.value.method?.id)
        assertTrue(events.indexOf("stop:wireguard_relay") < events.indexOf("start:vless:NL"))
        assertEquals(listOf("vless", "wireguard_relay"), preference.order(listOf("wireguard_relay", "vless")))
        controller.beforeLogout()
    }
    @Test fun transientOfflineAndUnknownResponsesDoNotPenalizeOrReconnect() = runTest {
        val events = mutableListOf<String>(); val adapter = Adapter("wireguard", events)
        var failureWrites = 0
        val preference = MethodPreference(writeFailures = { failureWrites++ })
        val controller = VpnController({ "owner" }, backgroundScope, listOf(adapter), preference, healthPolicy = policy)
        controller.connect("DE"); runCurrent()
        adapter.result = TunnelHealth.UNREACHABLE; advanceTimeBy(30); runCurrent()
        adapter.result = TunnelHealth.NO_NETWORK; advanceTimeBy(5); runCurrent()
        assertEquals(VpnPhase.WAITING_NETWORK, controller.status.value.phase)
        adapter.result = TunnelHealth.UNKNOWN; advanceTimeBy(5); runCurrent()
        adapter.result = TunnelHealth.HEALTHY; advanceTimeBy(30); runCurrent()
        assertEquals(VpnPhase.CONNECTED, controller.status.value.phase)
        assertEquals(1, events.count { it.startsWith("start:") }); assertEquals(0, failureWrites)
        controller.beforeLogout()
    }
    @Test fun deepSleepDoesNotBecomeATransportFailureOrChangeVerifiedStatus() = runTest {
        val events = mutableListOf<String>(); val adapter = Adapter("wireguard", events)
        val controller = VpnController({ "owner" }, backgroundScope, listOf(adapter), healthPolicy = policy.copy(intervalMillis = 30_000))
        controller.connect("DE"); runCurrent(); adapter.result = TunnelHealth.SUSPENDED
        advanceTimeBy(300_000); runCurrent()
        assertEquals(VpnPhase.CONNECTED, controller.status.value.phase)
        assertEquals(1, events.count { it.startsWith("start:") })
        adapter.result = TunnelHealth.HEALTHY; advanceTimeBy(30_000); runCurrent()
        assertEquals(VpnPhase.CONNECTED, controller.status.value.phase); controller.beforeLogout()
    }
    @Test fun manualDisconnectCancelsInFlightHealthAndDoesNotResurrect() = runTest {
        val events = mutableListOf<String>(); val adapter = Adapter("wireguard", events)
        adapter.probeGate = CompletableDeferred()
        val controller = VpnController({ "owner" }, backgroundScope, listOf(adapter), healthPolicy = policy)
        controller.connect("DE"); runCurrent(); advanceTimeBy(30); runCurrent()
        controller.disconnect(); runCurrent(); adapter.probeGate!!.complete(Unit); advanceTimeBy(1_000); runCurrent()
        assertEquals(VpnPhase.DISCONNECTED, controller.status.value.phase)
        assertEquals(1, events.count { it.startsWith("start:") })
    }
    @Test fun failedCleanupPreventsAnyReplacementTunnel() = runTest {
        val events = mutableListOf<String>(); val first = Adapter("wireguard", events); val next = Adapter("vless", events)
        val controller = VpnController({ "owner" }, backgroundScope, listOf(first, next), healthPolicy = policy)
        controller.connect("DE"); runCurrent(); first.result = TunnelHealth.UNREACHABLE; first.cleanupFails = true
        advanceTimeBy(40); runCurrent()
        assertEquals(VpnError.CLEANUP, controller.status.value.error)
        assertEquals(1, events.count { it.startsWith("start:") })
        first.cleanupFails = false; controller.beforeLogout()
    }
    @Test fun repeatedFlappingStopsAfterBoundedRecoveryBudget() = runTest {
        val events = mutableListOf<String>(); val adapter = Adapter("wireguard", events)
        adapter.result = TunnelHealth.UNREACHABLE
        val controller = VpnController({ "owner" }, backgroundScope, listOf(adapter), healthPolicy = policy, elapsedMillis = { testScheduler.currentTime })
        controller.connect("DE"); runCurrent(); advanceTimeBy(500); runCurrent()
        assertEquals(VpnError.UNSTABLE, controller.status.value.error)
        assertEquals(4, events.count { it.startsWith("start:") })
        assertEquals(4, events.count { it.startsWith("stop:") })
    }
    @Test fun resetClearsRememberedMethodsButPreservesEnabledSelection() = runTest {
        val events = mutableListOf<String>(); val first = Adapter("wireguard", events); val second = Adapter("vless", events)
        var saved = "vless"
        val preference = MethodPreference({ saved }, { saved = it })
        val controller = VpnController({ "owner" }, backgroundScope, listOf(first, second), preference, enabledMethods = { setOf("vless") }, healthPolicy = policy)
        controller.connect("DE"); runCurrent()
        controller.resetMethods("NL"); runCurrent()
        assertEquals(listOf("start:vless:DE", "stop:vless", "start:vless:NL"), events)
        assertEquals("vless", saved)
        controller.beforeLogout()
    }
    @Test fun manualDisconnectWinsOverPendingResetAndLateCleanup() = runTest {
        val events = mutableListOf<String>(); val adapter = Adapter("wireguard", events)
        val controller = VpnController({ "owner" }, backgroundScope, listOf(adapter), healthPolicy = policy)
        controller.connect("DE"); runCurrent(); adapter.cleanupGate = CompletableDeferred()
        controller.resetMethods("NL"); runCurrent(); controller.disconnect(); adapter.cleanupGate!!.complete(Unit); runCurrent()
        assertEquals(VpnPhase.DISCONNECTED, controller.status.value.phase)
        assertEquals(1, events.count { it.startsWith("start:") })
    }
    @Test fun accountChangeClosesTunnelWithoutAutomaticNewSession() = runTest {
        val events = mutableListOf<String>(); val adapter = Adapter("wireguard", events)
        var owner = "first"
        val controller = VpnController({ owner }, backgroundScope, listOf(adapter), healthPolicy = policy)
        controller.connect("DE"); runCurrent(); owner = "second"; advanceTimeBy(30); runCurrent()
        assertEquals(VpnError.ACCESS, controller.status.value.error)
        assertEquals(listOf("start:wireguard:DE", "stop:wireguard"), events)
    }
    @Test fun accountChangeDuringResetDoesNotLeaveAQueuedReconnect() = runTest {
        val events = mutableListOf<String>(); val adapter = Adapter("wireguard", events)
        var owner = "first"
        val controller = VpnController({ owner }, backgroundScope, listOf(adapter), healthPolicy = policy)
        controller.connect("DE"); runCurrent(); adapter.cleanupGate = CompletableDeferred()
        controller.resetMethods("NL"); runCurrent(); owner = "second"; adapter.cleanupGate!!.complete(Unit); runCurrent()
        assertEquals(VpnError.ACCESS, controller.status.value.error)
        assertEquals(listOf("start:wireguard:DE", "stop:wireguard"), events)
    }
    @Test fun nativeTransportLossTriggersAnEarlyCheckButStillRequiresConfirmation() = runTest {
        val events = mutableListOf<String>(); val adapter = Adapter("wireguard", events)
        val controller = VpnController({ "owner" }, backgroundScope, listOf(adapter), healthPolicy = policy)
        controller.connect("DE"); runCurrent(); controller.transportLost("wireguard"); runCurrent()
        assertEquals(VpnPhase.CONNECTED, controller.status.value.phase)
        assertEquals(1, events.count { it.startsWith("probe:") })
        assertEquals(1, events.count { it.startsWith("start:") }); controller.beforeLogout()
    }
}
