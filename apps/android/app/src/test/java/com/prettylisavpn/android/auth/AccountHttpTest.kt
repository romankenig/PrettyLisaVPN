package com.prettylisavpn.android.auth

import com.prettylisavpn.android.data.*
import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.*
import org.junit.Assert.*

class AccountHttpTest {
    private val server=MockWebServer()
    private lateinit var api: HttpAccountApi
    @Before fun start() { server.start();api=HttpAccountApi(HttpAuthApi(server.url("/").toString(),true),"0.5.0") }
    @After fun stop() { server.shutdown() }
    @Test fun deviceArrayAndRevokeTransport()=runBlocking {
        val id="20000000-0000-0000-0000-000000000002"
        val device="""{"id":"$id","device_name":"Phone","is_current":false,"created_at":"2026-10-20T00:00:00Z","last_login_at":null,"status":"ACTIVE"}"""
        server.enqueue(MockResponse().setBody("[$device]"));server.enqueue(MockResponse().setBody("""{"status":"revoked","device":${device.replace("ACTIVE","REVOKED")}}"""))
        assertNull(api.devices("synthetic").single().lastLogin);assertFalse(api.revoke("synthetic",id).active)
        assertEquals("Bearer synthetic",server.takeRequest().getHeader("Authorization"));assertEquals("DELETE",server.takeRequest().method)
    }
    @Test fun messagesContextBlocksAndAckReceipt()=runBlocking {
        val id="20000000-0000-0000-0000-000000000003"
        server.enqueue(MockResponse().setBody("""{"schema_version":1,"messages":[{"id":"$id","revision":3,"title":"Title","blocks":[{"type":"paragraph","text":"Body"},{"type":"list","items":["One"]}],"fallback_text":"Fallback","primary_action":{"type":"OPEN_SUBSCRIPTION","label":"Details"},"dismiss_label":"OK"}]}"""))
        server.enqueue(MockResponse().setBody("""{"id":"$id","revision":3,"acknowledged":true}"""))
        val m=api.messages("synthetic").single();assertEquals("SUBSCRIPTION",m.destination);assertTrue(m.body.contains("• One"));api.acknowledge("synthetic",id,3)
        assertTrue(server.takeRequest().path!!.contains("platform=ANDROID&app_version=0.5.0&locale=en&schema_version=1"));assertTrue(server.takeRequest().body.readUtf8().contains("\"revision\":3"))
    }
    @Test fun supportMultipartOmitsUnsupportedDiagnosticsAndLooksUpStatus()=runBlocking {
        val id="20000000-0000-0000-0000-000000000005"
        server.enqueue(MockResponse().setResponseCode(404).setBody("""{"error":{"code":"SUPPORT_NOT_FOUND"}}"""))
        server.enqueue(MockResponse().setResponseCode(202).setBody("""{"request_id":"$id","status":"ACCEPTED"}"""))
        assertNull(api.supportStatus("synthetic",id));api.supportSubmit("synthetic",SupportSubmission(id,"Subject","Body","reply@example.com",emptyList()))
        assertEquals("GET",server.takeRequest().method)
        val request=server.takeRequest();assertTrue(request.getHeader("Content-Type")!!.startsWith("multipart/form-data"))
        val body=request.body.readUtf8();assertTrue(body.contains("\"diagnostics\":null"));assertFalse(body.contains("WINDOWS"));assertTrue(body.contains("\"request_id\":\"$id\""))
    }
    @Test fun mismatchedAckReceiptFailsClosed()=runBlocking {
        server.enqueue(MockResponse().setBody("""{"id":"wrong","revision":3,"acknowledged":true}"""))
        try { api.acknowledge("synthetic","20000000-0000-0000-0000-000000000003",3);fail() } catch(e:AuthFailure) { assertEquals("invalid_response",e.code) }
    }
    @Test fun messagesUnauthorizedUsesBoundedSessionRecovery()=runBlocking {
        server.enqueue(MockResponse().setResponseCode(401).setBody("""{"error":{"code":"invalid_session"}}"""))
        try { api.messages("synthetic");fail() } catch(e:AuthFailure) { assertEquals("invalid_access_token",e.code) }
    }
    @Test fun countryAvailabilityAndUploadProgressUseExistingApi()=runBlocking {
        server.enqueue(MockResponse().setBody("""{"autopilot":{"quality":80,"available":true},"countries":[{"country_code":"DE","quality":80,"available":true}]}"""))
        assertEquals("DE",api.countries("synthetic").single().code)
        assertEquals("/vpn/countries",server.takeRequest().path)
        val id="20000000-0000-0000-0000-000000000005"
        server.enqueue(MockResponse().setBody("""{"request_id":"$id","status":"ACCEPTED"}"""))
        val events=mutableListOf<Pair<Long,Long>>()
        val report=SupportSubmission(id,"Synthetic",supportDescription("Body","{\"platform\":\"ANDROID\"}"),"reply@example.com",listOf(SupportUpload("image/png",java.util.Base64.getEncoder().encodeToString(ByteArray(8192)))))
        api.supportSubmit("synthetic",report) { sent,total -> events.add(sent to total) }
        assertEquals(0L,events.first().first);assertTrue(events.last().first>8192);assertEquals(events.last().second,events.last().first)
        val body=server.takeRequest().body.readUtf8();assertTrue(body.contains("Android diagnostics"));assertTrue(body.contains("\"diagnostics\":null"));assertFalse(body.contains("WINDOWS"))
    }

}
