package com.prettylisavpn.android.vpn

import kotlinx.coroutines.test.runTest
import org.junit.Assert.*
import org.junit.Test

class DisconnectCleanupTest {
    @Test fun localFailureStillRevokesRemoteAndCanBeRetried() = runTest {
        var revoked = false
        val failure = IllegalStateException("local stop failed")
        val result = runCatching { disconnectCleanup({ throw failure }, { revoked = true }) }
        assertTrue(revoked)
        assertSame(failure, result.exceptionOrNull())
        disconnectCleanup({}, {})
    }
    @Test fun uncertainRemoteRemovalNeverReportsSuccess() = runTest {
        var stopped = false
        val result = runCatching { disconnectCleanup({ stopped = true }, { error("offline") }) }
        assertTrue(stopped)
        assertTrue(result.isFailure)
    }
}
