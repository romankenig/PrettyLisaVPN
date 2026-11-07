package com.prettylisavpn.android.ui

import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import org.junit.Assert.*
import org.junit.Test
import kotlinx.coroutines.test.*

@OptIn(ExperimentalCoroutinesApi::class)
class ServerConnectionTest {
    @Test fun shortNetworkLossIsHiddenAndPersistentLossHasOneFifteenSecondDeadline() = runTest {
        val network = MutableStateFlow(true)
        val states = mutableListOf<Boolean>()
        val job = backgroundScope.launch { serverConnections(network) { true }.toList(states) }
        runCurrent()
        assertEquals(listOf(true), states)
        network.value = false; runCurrent()
        advanceTimeBy(14_999); runCurrent()
        assertEquals(listOf(true), states)
        network.value = true; runCurrent()
        assertEquals(listOf(true), states)
        network.value = false; runCurrent()
        advanceTimeBy(15_000); runCurrent()
        assertEquals(listOf(true, false), states)
        network.value = true; runCurrent()
        assertEquals(listOf(true, false, true), states)
        job.cancel()
    }
    @Test fun repeatedProbeFailuresDoNotRestartGraceAndRecoveryIsImmediate() = runTest {
        var available = false
        val states = mutableListOf<Boolean>()
        backgroundScope.launch { serverConnections(flowOf(true)) { available }.toList(states) }
        runCurrent(); advanceTimeBy(14_999); runCurrent()
        assertTrue(states.isEmpty())
        advanceTimeBy(1); runCurrent()
        assertEquals(listOf(false), states)
        available = true
        advanceTimeBy(3_000); runCurrent()
        assertEquals(listOf(false, true), states)
    }
    @Test fun serverFailureRetriesWithoutNetworkChangeAndRecovers() = runBlocking {
        var probes=0
        val states=withTimeout(2_000) { serverConnections(flowOf(true),1,0) {
            if (++probes == 1) throw java.io.IOException("timeout") else true
        }.take(2).toList() }
        assertEquals(listOf(false,true),states)
        assertEquals(2,probes)
    }
    @Test fun networkLossCancelsProbeAndNetworkReturnChecksAgain() = runBlocking {
        val network=MutableStateFlow(true)
        val entered=CompletableDeferred<Unit>()
        val cancelled=CompletableDeferred<Unit>()
        val states=mutableListOf<Boolean>()
        var probes=0
        val job=launch { serverConnections(network,1,0) {
            probes++
            if (probes == 1) {
                entered.complete(Unit)
                try { awaitCancellation() } finally { cancelled.complete(Unit) }
            } else true
        }.take(2).toList(states) }
        withTimeout(2_000) {
            entered.await();network.value=false;cancelled.await()
            while (states.isEmpty()) yield()
            network.value=true;job.join()
        }
        assertEquals(listOf(false,true),states)
        assertEquals(2,probes)
    }
    @Test fun offlineDoesNotProbeAndCollectorCancellationStopsPolling() = runTest {
        var probes=0
        assertEquals(false,serverConnections(flowOf(false),1,0) { probes++;true }.first())
        assertEquals(0,probes)
        assertTrue(serverConnections(flowOf(true),1) { probes++;true }.first())
        // Real 1 ms timers can enqueue another probe before first() resumes on a busy runner.
        // Virtual time keeps the same cancellation assertion independent of CPU scheduling.
        advanceTimeBy(10);runCurrent()
        assertEquals(1,probes)
    }
    @Test fun countryFlagsAcceptOnlyIsoCodes() {
        assertEquals("🇩🇪",countryFlag("DE"))
        assertEquals("🌐",countryFlag(null))
        assertEquals("🌐",countryFlag("AUTO"))
        assertEquals("🌐",countryFlag("de"))
    }
}
