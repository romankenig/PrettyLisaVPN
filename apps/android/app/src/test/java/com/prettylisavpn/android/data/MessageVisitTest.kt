package com.prettylisavpn.android.data

import java.time.Instant
import org.junit.Assert.*
import org.junit.Test

class MessageVisitTest {
    @Test fun mandatoryCannotBeDeferredAndLinksRejectExecutableSchemes() {
        val message=first.copy(dismissalMode=MessageDismissalMode.REQUIRE_LINK,links=listOf(MessageLink("Update","https://prettylisavpn.com/#latest")))
        val visit=MessageVisit();visit.defer(message)
        assertEquals(message,visit.next(listOf(message),now))
        assertFalse(visit.canClose(message))
        visit.linkOpened(message);assertTrue(visit.canClose(message));visit.defer(message)
        assertNull(visit.next(listOf(message),now))
        val nextVisit=MessageVisit();assertEquals(message,nextVisit.next(listOf(message),now));assertFalse(nextVisit.canClose(message))
        visit.reset();assertFalse(visit.canClose(message))
        assertTrue(validMessageUrl(message.links.single().url))
        for(url in listOf("http://example.com","javascript:alert(1)","file:///tmp/x","https://user@example.com","https://@example.com","https://example.com:8443","https://example.com\\@evil.com","https://example.com/\n")) assertFalse(validMessageUrl(url))
    }
    private val now=Instant.parse("2026-10-22T00:00:00Z")
    private val first=AccountMessage("id",1,"title","body",null,dismissalMode=MessageDismissalMode.NEXT_VISIT)
    @Test fun laterIsEphemeralAndRevisionSpecific() {
        val visit=MessageVisit();visit.defer(first)
        assertNull(visit.next(listOf(first),now))
        assertEquals(2,visit.next(listOf(first.copy(revision=2)),now)?.revision)
        assertEquals(first,MessageVisit().next(listOf(first),now))
        visit.reset();assertEquals(first,visit.next(listOf(first),now))
    }
    @Test fun onceRequiresAcknowledgementBeforeHiding() {
        val once=first.copy(dismissalMode=MessageDismissalMode.ONCE)
        val visit=MessageVisit();visit.defer(once)
        assertEquals(once,visit.next(listOf(once),now))
        visit.acknowledged(once);assertNull(visit.next(listOf(once),now))
        assertEquals(2,visit.next(listOf(once.copy(revision=2)),now)?.revision)
        val repeat=first.copy(id="repeat");visit.acknowledged(repeat)
        assertEquals(repeat,visit.next(listOf(repeat),now))
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
