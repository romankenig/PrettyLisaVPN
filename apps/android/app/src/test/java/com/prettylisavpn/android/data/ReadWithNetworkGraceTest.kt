package com.prettylisavpn.android.data

import com.prettylisavpn.android.auth.AuthFailure
import kotlinx.coroutines.test.runTest
import org.junit.Assert.*
import org.junit.Test

@OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
class ReadWithNetworkGraceTest {
    @Test fun transientReadFailureRecoversWithoutWarning() = runTest {
        var calls = 0
        assertEquals("ok", readWithNetworkGrace(now = { testScheduler.currentTime }) {
            if (++calls < 3) throw AuthFailure("offline") else "ok"
        })
        assertEquals(6_000L, testScheduler.currentTime)
    }
    @Test fun repeatedFailuresDoNotExtendGraceAndAuthErrorsAreImmediate() = runTest {
        var calls = 0
        try {
            readWithNetworkGrace(now = { testScheduler.currentTime }) { calls++; throw AuthFailure("network_uncertain") }
            fail("Expected offline error")
        } catch (error: AuthFailure) { assertEquals("network_uncertain", error.code) }
        assertEquals(15_000L, testScheduler.currentTime)
        assertEquals(6, calls)
        try {
            readWithNetworkGrace(now = { testScheduler.currentTime }) { throw AuthFailure("invalid_session") }
        } catch (error: AuthFailure) { assertEquals("invalid_session", error.code) }
        assertEquals(15_000L, testScheduler.currentTime)
    }
}
