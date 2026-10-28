package com.prettylisavpn.android

import com.prettylisavpn.android.auth.*
import com.prettylisavpn.android.vpn.WireGuardApi
import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Test
import org.junit.Assert.*

class WireGuardApiTest {
    @Test fun customerLeaseUsesAuthenticatedIdempotencyAndConfirmedRemoval() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            val sessions = SessionCoordinator(FakeApi(), MemoryVault(), "Test")
            sessions.login("test@example.com", "123456")
            val api = WireGuardApi(HttpAuthApi(server.url("/").toString(), true), sessions)
            val id = "10000000-0000-0000-0000-000000000001"
            fun row(state: String) = """{"id":"$id","status":"$state","country":"DE","expires_at":"2030-01-01T00:00:00Z","heartbeat_seconds":30}"""
            server.enqueue(MockResponse().setBody("null"))
            assertNull(api.current())
            assertEquals("/vpn/wireguard/sessions/current", server.takeRequest().path)
            server.enqueue(MockResponse().setResponseCode(202).setBody(row("PROVISIONING")))
            assertEquals("PROVISIONING", api.connect("DE", "public-only", id).status)
            val request = server.takeRequest()
            assertEquals("Bearer access-1", request.getHeader("Authorization"))
            assertEquals(id, request.getHeader("Idempotency-Key"))
            val body = request.body.readUtf8()
            assertTrue(body.contains("public-only")); assertFalse(body.contains("private"))
            assertTrue(body.contains("\"method\":\"wireguard\""))
            server.enqueue(MockResponse().setResponseCode(202).setBody(row("PROVISIONING")))
            api.connect("DE", "public-only", id, "wireguard_relay")
            assertTrue(server.takeRequest().body.readUtf8().contains("\"method\":\"wireguard_relay\""))
            server.enqueue(MockResponse().setBody(row("READY")))
            assertEquals("READY", api.heartbeat(id).status)
            assertEquals("POST", server.takeRequest().method)
            server.enqueue(MockResponse().setBody(row("REVOKING")))
            assertEquals("REVOKING", api.revoke(id).status)
            assertEquals("DELETE", server.takeRequest().method)
            server.enqueue(MockResponse().setBody(row("CLOSED")))
            assertEquals("CLOSED", api.get(id).status)
        } finally { server.shutdown() }
    }
}
