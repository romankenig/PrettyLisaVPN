package com.prettylisavpn.android.data

import java.time.Instant
import org.junit.Assert.*
import org.junit.Test

class MessageVisitTest {
    private val now=Instant.parse("2026-10-22T00:00:00Z")
    private val first=AccountMessage("id",1,"title","body",null)
    @Test fun laterIsEphemeralAndRevisionSpecific() {
        val visit=MessageVisit();visit.defer(first)
        assertNull(visit.next(listOf(first),now))
        assertEquals(2,visit.next(listOf(first.copy(revision=2)),now)?.revision)
        assertEquals(first,MessageVisit().next(listOf(first),now))
        visit.reset();assertEquals(first,visit.next(listOf(first),now))
    }
    @Test fun popupQueueSkipsExpiredMessagesAndKeepsServerOrder() {
        val visit=MessageVisit()
        val expired=first.copy(expiresAt=now.toString())
        val next=first.copy(id="next",expiresAt=now.plusSeconds(1).toString())
        assertEquals(next,visit.next(listOf(expired,next,first),now))
        assertFalse(MessageVisit.fresh(first.copy(expiresAt="invalid"),now))
        assertNull(visit.next(listOf(expired),now))
    }
}
