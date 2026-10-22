package com.prettylisavpn.android

import com.prettylisavpn.android.auth.*
import com.prettylisavpn.android.vpn.*
import com.google.gson.JsonParser
import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.*
import org.junit.Test

class VpnApiTest {
    private val raw = """{"session_id":"d84cd4d2-8aee-4c17-9772-31db1d512924","status":"ACTIVE","country_code":"DE","server_time":"2026-10-22T00:00:00Z","expires_at":null,"transport":{"endpoint":{"ipv4":"203.0.113.1","port":51820},"server_public_key":"AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE=","client_address":"10.77.0.2/32","dns":["1.1.1.1"],"allowed_ips":["0.0.0.0/0"]},"candidates":[{"country":"DE","protocol":"WIREGUARD","transport":"UDP","port":51820,"encryption_mode":"WIREGUARD","obfuscation_mode":"NONE","mtu":1280,"dns_mode":"VPN","routing_mode":"FULL_TUNNEL"}]}"""
    @Test fun explicitDirectIpv4ProfileIsAccepted() { assertEquals(51820, parseVpnSession(raw).config!!.port) }
    @Test fun emptyMissingLegacyAndUnsupportedFirstCandidateNeverFallback() {
        for (variant in listOf(raw.replace("\"candidates\":[{", "\"candidates\":[{"), raw)) assertNotNull(parseVpnSession(variant).config)
        val empty = JsonParser.parseString(raw).asJsonObject.apply { add("candidates", com.google.gson.JsonArray()) }
        assertNull(parseVpnSession(empty).config); empty.remove("candidates"); assertNull(parseVpnSession(empty).config)
        val legacy = raw.replace("\"UDP\"", "\"NATIVE\"").replace("\"NONE\"", "\"NATIVE\"")
        assertNull(parseVpnSession(legacy).config)
        val first = JsonParser.parseString(raw).asJsonObject
        val supported = first.getAsJsonArray("candidates")[0].deepCopy()
        first.getAsJsonArray("candidates")[0].asJsonObject.addProperty("protocol", "OPENVPN")
        first.getAsJsonArray("candidates").add(supported)
        assertNull(parseVpnSession(first).config)
    }
    @Test fun invalidRoutesDnsKeysCountryAndPortAreRejectedButIdIsRetained() {
        for (variant in listOf(raw.replace("0.0.0.0/0", "0.0.0.0/1"), raw.replace("1.1.1.1", "::1"), raw.replace("10.77.0.2/32", "10.77.0.2/24"), raw.replace("203.0.113.1", "host.invalid"), raw.replace("\"mtu\":1280", "\"mtu\":1400"), raw.replace("AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE=", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="))) {
            val session = parseVpnSession(variant); assertNotNull(session.id); assertNull(session.config)
        }
    }
    @Test fun createCurrentDeleteUseExistingContractAndCandidateHeader() = runBlocking {
        val server = MockWebServer(); server.start()
        try {
            val vault = object : CredentialVault {
                var value: Credentials? = Credentials("d84cd4d2-8aee-4c17-9772-31db1d512924", "test", "2040-01-01T00:00:00Z")
                override fun read() = value; override fun write(credentials: Credentials) { value=credentials }; override fun clear() { value=null }; override fun installationId()="test"
            }
            val auth = object : AuthApi {
                override suspend fun requestOtp(email:String) = Unit
                override suspend fun verifyOtp(email:String,code:String,installationId:String,deviceName:String): Tokens = error("no OTP")
                override suspend fun refresh(credentials:Credentials)=Tokens("synthetic-access",3600,credentials)
                override suspend fun me(access:String)=Profile("test@example.com","Free",1,"owner")
                override suspend fun logout(access:String)=Unit
            }
            val sessions = SessionCoordinator(auth, vault, "test"); sessions.restore()
            val api = HttpVpnApi(HttpAuthApi(server.url("/").toString(),true),sessions)
            server.enqueue(MockResponse().setBody(raw)); val created=api.create("DE", "test-public")
            val request=server.takeRequest(); assertEquals("/vpn/sessions",request.path); assertEquals("1",request.getHeader("X-VPN-Candidates")); assertEquals("Bearer synthetic-access",request.getHeader("Authorization"))
            val body=JsonParser.parseString(request.body.readUtf8()).asJsonObject; assertEquals(setOf("mode","country_code","public_key"),body.keySet()); assertEquals("COUNTRY",body.get("mode").asString)
            server.enqueue(MockResponse().setBody("{\"session\":$raw}")); assertEquals(created.id,api.current()!!.id); assertEquals("1",server.takeRequest().getHeader("X-VPN-Candidates"))
            server.enqueue(MockResponse().setBody("""{"session_id":"${created.id}","status":"DISCONNECTED"}""")); api.delete(created.id); assertEquals("DELETE",server.takeRequest().method)
            server.enqueue(MockResponse().setResponseCode(404).setBody("""{"error":{"code":"VPN_SESSION_NOT_FOUND"}}""")); api.delete(created.id)
        } finally { server.shutdown() }
    }
}
