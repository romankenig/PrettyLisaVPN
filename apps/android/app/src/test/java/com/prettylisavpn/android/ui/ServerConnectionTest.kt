package com.prettylisavpn.android.ui

import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import org.junit.Assert.*
import org.junit.Test

class ServerConnectionTest {
    @Test fun serverFailureRetriesWithoutNetworkChangeAndRecovers() = runBlocking {
        var probes=0
        val states=withTimeout(2_000) { serverConnections(flowOf(true),1) {
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
        val job=launch { serverConnections(network,1) {
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
    @Test fun offlineDoesNotProbeAndCollectorCancellationStopsPolling() = runBlocking {
        var probes=0
        assertEquals(false,serverConnections(flowOf(false),1) { probes++;true }.first())
        assertEquals(0,probes)
        assertTrue(serverConnections(flowOf(true),1) { probes++;true }.first())
        delay(10)
        assertEquals(1,probes)
    }
    @Test fun countryFlagsAcceptOnlyIsoCodes() {
        assertEquals("🇩🇪",countryFlag("DE"))
        assertEquals("🌐",countryFlag(null))
        assertEquals("🌐",countryFlag("AUTO"))
        assertEquals("🌐",countryFlag("de"))
    }
}
