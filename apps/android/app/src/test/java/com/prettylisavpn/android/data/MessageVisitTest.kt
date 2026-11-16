package com.prettylisavpn.android.data

import java.time.Instant
import org.junit.Assert.*
import org.junit.Test

class MessageVisitTest {
    @Test fun mandatoryCannotBeDeferredAndLinksRejectExecutableSchemes() {
        val message=first.copy(dismissible=false,links=listOf(MessageLink("Update","https://prettylisavpn.com/#latest")))
        val visit=MessageVisit();visit.defer(message)
        assertEquals(message,visit.next(listOf(message),now))
        assertTrue(validMessageUrl(message.links.single().url))
        for(url in listOf("http://example.com","javascript:alert(1)","file:///tmp/x","https://user@example.com","https://@example.com","https://example.com:8443","https://example.com\\@evil.com","https://example.com/\n")) assertFalse(validMessageUrl(url))
    }
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
