package com.prettylisavpn.android.ui

import kotlinx.coroutines.*
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.runCurrent
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class LocationRefreshTest {
    @Test fun newConnectionClearsOldIpAndRejectsLateOldRouteResponse() = runTest {
        val old = CompletableDeferred<String?>()
        var calls = 0
        val location = LocationRefresh { if (++calls == 1) old.await() else "VPN IP" }
        val initial = launch { location.refresh() }
        runCurrent()
        assertTrue(location.loading.value)
        location.invalidate(true)
        location.refresh()
        assertEquals("VPN IP", location.value.value)
        old.complete("old IP"); initial.join()
        assertEquals("VPN IP", location.value.value)
        assertFalse(location.loading.value)
        location.invalidate(false)
        assertNull(location.value.value)
    }
    @Test fun failedOrCancelledLookupDoesNotLeaveSpinnerOrStaleValue() = runTest {
        var block = false
        val location = LocationRefresh { if (block) awaitCancellation() else "IP" }
        location.refresh()
        block = true
        val refresh = launch { location.refresh() }
        runCurrent()
        assertNull(location.value.value)
        assertTrue(location.loading.value)
        refresh.cancelAndJoin()
        assertFalse(location.loading.value)
    }
}
