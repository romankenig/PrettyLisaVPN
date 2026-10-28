package com.prettylisavpn.android.vpn

import com.prettylisavpn.android.auth.AuthFailure
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test

class LeaseHeartbeatTest {
    @Test fun sleepTolerantAccessSurvivesLongSilenceAndTransientFailures() = runBlocking {
        var calls = 0; var lost = 0
        withTimeout(2_000) {
            maintainLeaseHeartbeat(1, 1, 10, heartbeatRequired = false, renew = {
                when (++calls) {
                    1 -> { delay(100); true } // Longer than the legacy budget, e.g. resumed after sleep.
                    2 -> throw AuthFailure("offline")
                    3 -> throw AuthFailure("network_uncertain")
                    4 -> throw AuthFailure("service_unavailable")
                    5 -> throw AuthFailure("rotation_uncertain") // Never replay an ambiguous refresh.
                    6 -> true
                    else -> false // A confirmed revoked/expired lease still ends the tunnel.
                }
            }, lost = { lost++ })
        }
        assertEquals(7, calls); assertEquals(1, lost)
    }

    @Test fun sleepTolerantAccessStillStopsOnRevocationAndCancelsPromptly() = runBlocking {
        for (code in listOf("device_revoked", "user_blocked", "invalid_session", "reauth_required", "VPN_SESSION_NOT_FOUND")) {
            var calls = 0; var lost = 0
            maintainLeaseHeartbeat(1, 1, 10, heartbeatRequired = false,
                renew = { calls++; throw AuthFailure(code) }, lost = { lost++ })
            assertEquals(code, 1, calls); assertEquals(code, 1, lost)
        }
        val entered = CompletableDeferred<Unit>(); var lost = 0
        val job = launch {
            maintainLeaseHeartbeat(1, 1, 10, heartbeatRequired = false,
                renew = { entered.complete(Unit); awaitCancellation() }, lost = { lost++ })
        }
        withTimeout(2_000) { entered.await(); job.cancelAndJoin() }
        assertEquals(0, lost)
    }

    @Test fun absentServerCapabilityPreservesLegacyBehavior() {
        val json = """{"id":"00000000-0000-0000-0000-000000000001","status":"READY","country":"DE","expires_at":"2026-10-28T12:00:00Z","heartbeat_seconds":30}"""
        val gson = com.google.gson.Gson()
        assertNull(gson.fromJson(json, WireGuardLease::class.java).heartbeat_required)
        assertEquals(false, gson.fromJson(json.dropLast(1) + ",\"heartbeat_required\":false}", WireGuardLease::class.java).heartbeat_required)
    }

    @Test fun temporaryFailureRetriesAndEachAcknowledgementStartsANewBudget() = runBlocking {
        var calls = 0; var lost = 0
        withTimeout(2_000) {
            maintainLeaseHeartbeat(1, 1, 1_000, renew = {
                when (++calls) {
                    1 -> throw AuthFailure("network_uncertain")
                    2 -> true
                    3 -> throw AuthFailure("offline")
                    4 -> true
                    else -> false // Confirmed remote revocation still stops immediately.
                }
            }, lost = { lost++ })
        }
        assertEquals(5, calls); assertEquals(1, lost)
    }

    @Test fun repeatedOutageExhaustsBudgetInsteadOfKeepingAnUnrenewedTunnel() = runBlocking {
        var calls = 0; var lost = 0
        withTimeout(2_000) {
            maintainLeaseHeartbeat(1, 5, 100, renew = {
                calls++; throw AuthFailure("service_unavailable")
            }, lost = { lost++ })
        }
        assertTrue(calls > 1); assertEquals(1, lost)
    }

    @Test fun invalidAccountAndAmbiguousRefreshAreNotRetried() = runBlocking {
        for (code in listOf("device_revoked", "user_blocked", "invalid_session", "rotation_uncertain", "invalid_response")) {
            var calls = 0; var lost = 0
            maintainLeaseHeartbeat(1, 1, 1_000, renew = {
                calls++; throw AuthFailure(code)
            }, lost = { lost++ })
            assertEquals(code, 1, calls); assertEquals(code, 1, lost)
        }
    }

    @Test fun cancellationDoesNotRetryOrReportConnectionLoss() = runBlocking {
        val entered = CompletableDeferred<Unit>(); var lost = 0
        val job = launch {
            maintainLeaseHeartbeat(1, 1, 1_000, renew = {
                entered.complete(Unit); awaitCancellation()
            }, lost = { lost++ })
        }
        withTimeout(2_000) { entered.await(); job.cancelAndJoin() }
        assertEquals(0, lost)
    }

    @Test fun blockedRenewalIsAlsoBoundedByTheLeaseBudget() = runBlocking {
        var lost = 0
        withTimeout(2_000) {
            maintainLeaseHeartbeat(1, 1, 100, renew = { awaitCancellation() }, lost = { lost++ })
        }
        assertEquals(1, lost)
    }
}
