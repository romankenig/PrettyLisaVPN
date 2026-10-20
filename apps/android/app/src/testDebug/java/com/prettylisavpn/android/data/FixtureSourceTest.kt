package com.prettylisavpn.android.data

import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test

class FixtureSourceTest {
    @Test fun renewalIsAppliedOnceAndCancellationKeepsPaidTime() = runBlocking {
        val source = FixtureSource(0)
        val renewal = Command.Payment("stable-id", "RENEW", "BANK_CARD", "USD")
        val first = source.execute(renewal)
        assertEquals("2026-12-20T00:00:00Z", first.paidUntil)
        assertEquals(first.paidUntil, source.execute(renewal).paidUntil)
        val changed = source.execute(Command.Payment("method", "CHANGE_METHOD", "BANK_CARD", "USD"))
        assertEquals(first.paidUntil, changed.paidUntil)
        val cancelled = source.execute(Command.Payment("cancel", "CANCEL", "", ""))
        assertEquals(first.paidUntil, cancelled.paidUntil)
        assertFalse(cancelled.autoRenew)
    }
    @Test fun pendingAndFailureDoNotGrantTimePrematurely() = runBlocking {
        val source = FixtureSource(0)
        source.configure(Scenario.PAYMENT_PENDING)
        val before = source.initial.paidUntil
        val payment = Command.Payment("pending", "RENEW", "MIR", "RUB")
        assertEquals(before, source.execute(payment).paidUntil)
        source.configure(Scenario.FAIL_NEXT)
        try { source.execute(Command.ConfirmPayment); fail("Expected simulated failure") } catch (_: SourceFailure) { }
        assertEquals(before, source.initial.paidUntil)
        val confirmed = source.execute(Command.ConfirmPayment)
        assertNotEquals(before, confirmed.paidUntil)
        assertEquals(confirmed.paidUntil, source.execute(Command.ConfirmPayment).paidUntil)
    }
    @Test fun capabilitiesAndFreeCountriesAreEnforcedBySource() = runBlocking {
        val source = FixtureSource(0)
        source.configure(Scenario.FREE)
        try { source.execute(Command.SelectCountry("DE")); fail("Free cannot select country") } catch (_: SourceFailure) { }
        try { source.execute(Command.Payment("bad", "SUBSCRIBE", "MIR", "USD")); fail("Unsupported currency") } catch (_: SourceFailure) { }
        val result = source.execute(Command.Payment("one-time", "SUBSCRIBE", "CRYPTO", "USD"))
        assertFalse(result.autoRenew)
        assertEquals("Premium", result.plan)
    }
    @Test fun revocationAndMessageRevisionsStayScoped() = runBlocking {
        val source = FixtureSource(0)
        val message = source.initial.messages.first()
        assertEquals(2, source.execute(Command.Acknowledge(message.id, message.revision + 1)).messages.size)
        assertEquals(1, source.execute(Command.Acknowledge(message.id, message.revision)).messages.size)
        val current = source.initial.devices.first { it.current }
        val revoked = source.execute(Command.Revoke(current.id))
        assertFalse(revoked.signedIn)
        assertFalse(revoked.simulatedConnection)
        try { source.execute(Command.ToggleConnection); fail("Requires test auth") } catch (_: SourceFailure) { }
    }
    @Test fun receiptsAreIdempotentAndRestartIsExplicitlyEphemeral() = runBlocking {
        val source = FixtureSource(0)
        val request = Command.Support("draft-id", "Subject", "Description", "test@example.invalid", 3)
        assertEquals("draft-id", source.execute(request).supportReceipt)
        assertEquals("draft-id", source.execute(request).supportReceipt)
        try { source.execute(request.copy(subject = "Changed")); fail("Request conflict") } catch (_: SourceFailure) { }
        assertTrue(source.execute(Command.SupportStatus).supportDelivered)
        assertNull(FixtureSource(0).initial.supportReceipt)
    }
}
