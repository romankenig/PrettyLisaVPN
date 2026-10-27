package com.prettylisavpn.android.vpn

import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test

class VpnDeadlineTest {
    @Test fun expiredAdapterIsFailureSoFallbackCanContinue() = runBlocking {
        val error = runCatching { vpnDeadline(10) { awaitCancellation() } }.exceptionOrNull()
        assertTrue(error is VpnOperationTimeout)
        assertFalse(error is CancellationException)
        assertTrue(currentCoroutineContext().isActive)
    }

    @Test fun ownerCancellationIsNotConvertedToFailedAttempt() = runBlocking {
        val child = async(start = CoroutineStart.UNDISPATCHED) { vpnDeadline(10_000) { awaitCancellation() } }
        child.cancel()
        val error = runCatching { child.await() }.exceptionOrNull()
        assertTrue(error is CancellationException)
        assertFalse(error is VpnOperationTimeout)
    }

    @Test fun outerDeadlineKeepsOwnershipOfCancellation() = runBlocking {
        val error = runCatching { withTimeout(10) { vpnDeadline(10_000) { awaitCancellation() } } }.exceptionOrNull()
        assertTrue(error is TimeoutCancellationException)
        assertFalse(error is VpnOperationTimeout)
    }
}
