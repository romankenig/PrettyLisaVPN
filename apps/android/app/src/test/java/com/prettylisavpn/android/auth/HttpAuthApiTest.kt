package com.prettylisavpn.android.auth

import com.google.gson.JsonParser
import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.*
import org.junit.Assert.*

class HttpAuthApiTest {
    private val server = MockWebServer()
    private lateinit var api: HttpAuthApi
    @Before fun start() { server.start(); api = HttpAuthApi(server.url("/api/").toString(), true) }
    @After fun stop() { server.shutdown() }
    private val tokens = """{"token_type":"bearer","access_token":"bearer-private","access_token_expires_in":60,"session_id":"c21132ac-0d2e-4da7-96ac-8a6ceeb019ba","refresh_token":"refresh-private","refresh_token_expires_at":"2030-01-01T00:00:00Z","extra":"ignored"}"""
    @Test fun otpContractHasAndroidPlatformAndStableInstallation() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(202).setBody("""{"status":"accepted"}"""))
        server.enqueue(MockResponse().setBody(tokens))
        api.requestOtp("person@example.com"); api.verifyOtp("person@example.com", "123456", "a1d3475f-0155-49e9-88a9-27125a19b12d", "Test phone")
        val request = server.takeRequest(); assertEquals("/api/auth/request-otp", request.path); assertNull(request.getHeader("Authorization"))
        val verify = server.takeRequest(); val json = JsonParser.parseString(verify.body.readUtf8()).asJsonObject
        assertEquals("/api/auth/verify-otp", verify.path); assertEquals("ANDROID", json["platform"].asString)
        assertEquals("123456", json["code"].asString); assertEquals("a1d3475f-0155-49e9-88a9-27125a19b12d", json["installation_id"].asString)
    }
    @Test fun refreshContractAndBearerScope() = runBlocking {
        server.enqueue(MockResponse().setBody(tokens)); server.enqueue(MockResponse().setBody("""{"id":"c21132ac-0d2e-4da7-96ac-8a6ceeb019ba","email":"person@example.com","plan":"FREE","active_device_count":1,"entitlements":{"extra":true}}"""))
        val result = api.refresh(Credentials("c21132ac-0d2e-4da7-96ac-8a6ceeb019ba", "old-private", "2030-01-01T00:00:00Z"))
        assertEquals("Free", api.me(result.access).plan)
        val refresh = server.takeRequest(); assertNull(refresh.getHeader("Authorization")); assertEquals("old-private", JsonParser.parseString(refresh.body.readUtf8()).asJsonObject["refresh_token"].asString)
        assertEquals("Bearer bearer-private", server.takeRequest().getHeader("Authorization"))
    }
    @Test fun redirectsCannotLeakBearerOrReplayOtp() = runBlocking {
        val other = MockWebServer(); other.start()
        try {
            server.enqueue(MockResponse().setResponseCode(307).setHeader("Location", other.url("/steal")))
            try { api.me("private"); fail() } catch (e: AuthFailure) { assertEquals("http_error", e.code) }
            assertEquals(0, other.requestCount); assertEquals(1, server.requestCount)
        } finally { other.shutdown() }
    }
    @Test fun machineErrorsNeverExposeRawServerBody() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(403).setBody("""{"error":{"code":"device_revoked"},"secret":"DO_NOT_RENDER"}"""))
        try { api.me("private"); fail() } catch (e: AuthFailure) { assertEquals("device_revoked", e.code); assertFalse(e.message!!.contains("DO_NOT_RENDER")) }
    }
    @Test fun logoutUsesBearerAndReceipt() = runBlocking {
        server.enqueue(MockResponse().setBody("""{"status":"logged_out"}""")); api.logout("private")
        val request = server.takeRequest(); assertEquals("/api/auth/logout", request.path); assertEquals("POST", request.method); assertEquals("Bearer private", request.getHeader("Authorization"))
    }
    @Test fun malformedSuccessFailsClosed() = runBlocking {
        server.enqueue(MockResponse().setBody("""{"access_token":"private"}"""))
        try { api.verifyOtp("person@example.com", "123456", "id", "phone"); fail() } catch (e: AuthFailure) { assertEquals("invalid_response", e.code) }
    }
    @Test fun unexpectedJsonShapeDoesNotExposeBody() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(202).setBody("[\"PRIVATE_BODY\"]"))
        try { api.requestOtp("person@example.com"); fail() } catch (e: AuthFailure) { assertEquals("invalid_response", e.code); assertFalse(e.message!!.contains("PRIVATE_BODY")) }
    }
    @Test fun apiRequiresHttpsAndRejectsEmbeddedCredentials() {
        for (url in listOf("http://example.com/", "https://user:pass@example.com/", "https://example.com/?token=private")) {
            try { HttpAuthApi(url); fail(url) } catch (_: IllegalArgumentException) { }
        }
    }
}
