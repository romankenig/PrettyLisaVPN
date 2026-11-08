package com.prettylisavpn.android

import com.google.gson.Gson
import com.prettylisavpn.android.diagnostics.*
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.time.Instant
import java.time.Duration

class DiagnosticJournalTest {
    @get:Rule val temporary = TemporaryFolder()
    private var now = Instant.parse("2026-11-08T12:00:00Z")
    private fun event(n: Long) = DiagnosticEvent(now.toString(), n, DiagnosticKind.VPN_HEALTH,
        method = "wireguard", outcome = DiagnosticOutcome.UNREACHABLE, duration_ms = 5000)

    @Test fun boundedStorageRetainsRecentEventsAndSurvivesRestart() {
        val directory = temporary.newFolder()
        val journal = DiagnosticJournal(directory, { now }, 4096)
        repeat(1000) { journal.append(event(it.toLong())) }
        assertTrue(directory.walk().filter { it.isFile }.sumOf { it.length() } <= 4096)
        val restored = DiagnosticJournal(directory, { now }, 4096).snapshot()
        assertEquals(999L, restored.events.last().elapsed_ms)
        assertTrue(restored.events.size < 1000)
    }

    @Test fun retentionAndExportBoundsAreExplicit() {
        val journal = DiagnosticJournal(temporary.newFolder(), { now })
        repeat(450) { journal.append(event(it.toLong())) }
        val snapshot = journal.snapshot()
        assertEquals(400, snapshot.events.size)
        assertEquals(50, snapshot.omitted_events)
        now = now.plus(Duration.ofDays(8))
        journal.append(event(999))
        assertEquals(listOf(999L), journal.snapshot().events.map { it.elapsed_ms })
        journal.clear()
        assertTrue(journal.snapshot().events.isEmpty())
    }

    @Test fun exceptionTextAndExternalFramesNeverEnterTheJournal() {
        val error = java.io.IOException("token=secret https://private.example/path OTP=123456")
        error.stackTrace = arrayOf(
            StackTraceElement("com.prettylisavpn.android.vpn.Example", "connect", "private-name", 42),
            StackTraceElement("external.Secret", "other", "private-name", 5))
        val data = DiagnosticEvent(now.toString(), 10, DiagnosticKind.APP_ERROR,
            failure = diagnosticFailure(error), frames = diagnosticFrames(error))
        val json = Gson().toJson(data.checked())
        assertEquals(1, data.frames!!.size)
        for (secret in listOf("secret", "private.example", "123456", "private-name", "external.Secret")) assertFalse(json.contains(secret))
        assertEquals(DiagnosticFailure.NETWORK, data.failure)
        assertEquals(DiagnosticOperation.OTHER, diagnosticOperation("https://private.example"))
        try { event(1).copy(country="https://private.example").checked(); fail() } catch (_: IllegalArgumentException) { }
    }
}
