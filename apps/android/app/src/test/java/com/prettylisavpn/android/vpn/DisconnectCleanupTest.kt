package com.prettylisavpn.android.vpn

import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test

class DisconnectCleanupTest {
    @Test fun localFailureStillRevokesRemoteAndCanBeRetried() = runBlocking {
        var revoked = false
        val failure = IllegalStateException("local stop failed")
        val result = runCatching { disconnectCleanup({ throw failure }, { revoked = true }) }
        assertTrue(revoked)
        assertSame(failure, result.exceptionOrNull())
        disconnectCleanup({}, {})
    }
    @Test fun uncertainRemoteRemovalNeverReportsSuccess() = runBlocking {
        var stopped = false
        val result = runCatching { disconnectCleanup({ stopped = true }, { error("offline") }) }
        assertTrue(stopped)
        assertTrue(result.isFailure)
    }
}
