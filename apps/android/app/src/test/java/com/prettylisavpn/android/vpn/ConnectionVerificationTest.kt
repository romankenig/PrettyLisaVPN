package com.prettylisavpn.android.vpn

import java.io.IOException
import java.net.UnknownHostException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test

class ConnectionVerificationTest {
    @Test fun transientDnsFailureRetriesTheSameLiveTunnel() = runBlocking {
        var probes = 0; var pauses = 0
        assertTrue(verifyConnection(isUp = { true }, pause = { pauses++ }) {
            if (++probes == 1) throw UnknownHostException()
            true
        })
        assertEquals(2, probes); assertEquals(1, pauses)
    }
    @Test fun egressMismatchAndCancellationDoNotRetry() = runBlocking {
        var probes = 0
        assertFalse(verifyConnection(isUp = { true }, pause = { fail("Unexpected retry") }) { probes++; false })
        assertEquals(1, probes)
        try {
            verifyConnection(isUp = { true }, pause = { fail("Cancellation retried") }) { throw CancellationException() }
            fail("Cancellation swallowed")
        } catch (_: CancellationException) { }
    }
    @Test fun persistentFailureIsBoundedAndAStoppedTunnelIsNeverRetried() = runBlocking {
        var probes = 0
        try {
            verifyConnection(isUp = { true }, pause = {}) { probes++; throw IOException() }
            fail("Persistent outage accepted")
        } catch (_: IOException) { assertEquals(2, probes) }
        for (stopDuringPause in listOf(false, true)) {
            probes = 0; var up = stopDuringPause
            try {
                verifyConnection(isUp = { up }, pause = { up = false }) { probes++; throw IOException() }
                fail("Stopped tunnel accepted")
            } catch (_: IOException) { assertEquals(1, probes) }
        }
    }
}
