package com.prettylisavpn.android.auth

import com.prettylisavpn.android.vpn.*
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test

class DemoTest {
    @Test fun identityIsStableAndHasNoInstallationRandomness() {
        assertEquals(demoDeviceHash("1234abcd"), demoDeviceHash("1234ABCD"))
        assertNotEquals(demoDeviceHash("1234abcd"), demoDeviceHash("1234abce"))
        assertTrue(demoDeviceHash("1234abcd").matches(Regex("[a-f0-9]{64}")))
        for (id in listOf(null, "", "0000000000000000", "not-a-device")) {
            try { demoDeviceHash(id); fail("Invalid identifier accepted") } catch (e: AuthFailure) { assertEquals("demo_identity_unavailable", e.code) }
        }
    }
    @Test fun demoAlwaysUsesAllTrafficButRetainsRegisteredPreferences() {
        val saved = TrafficSelection(mode = "include", include = TrafficList(masks = listOf("example.com")))
        assertEquals(RoutingPolicy("all", emptyList()), routingForPlan(true, saved))
        assertEquals(saved.policy(), routingForPlan(false, saved))
        assertEquals("include", saved.mode)
    }
    @Test fun guestCredentialsPersistAndFreeLoginGetsSeparateBudget() = runBlocking {
        val vault = MemoryVault()
        var guest = true
        var demos = 0
        var otps = 0
        val tokens = Tokens("test-access",900,Credentials("30000000-0000-0000-0000-000000000002","test-refresh","2030-01-01T00:00:00Z"))
        val api = object : AuthApi {
            override suspend fun demo(deviceKey: String): Tokens { assertEquals("a".repeat(64),deviceKey); demos++;return tokens }
            override suspend fun requestOtp(email: String) { otps++ }
            override suspend fun verifyOtp(email: String, code: String, installationId: String, deviceName: String): Tokens { guest = false;return tokens }
            override suspend fun refresh(credentials: Credentials) = tokens
            override suspend fun me(access: String): Profile {
                assertNotNull(vault.value)
                return Profile(if (guest) "" else "account@example.com",if (guest) "Demo" else "Free",1,
                    if (guest) "guest" else "registered", FreeTime(if (guest) 123 else 3600,0,"2030-01-01T00:00:00Z",0,if (guest) 900 else 3600))
            }
            override suspend fun logout(access: String) = Unit
        }
        val coordinator = SessionCoordinator(api,vault,"test",demoIdentity = { "a".repeat(64) })
        assertTrue(coordinator.demo().isDemo)
        assertEquals(0,otps); assertEquals(1,demos)
        val restarted = SessionCoordinator(api,vault,"test")
        assertEquals(123,restarted.restore()!!.freeTime!!.seconds)
        assertEquals(1,demos)
        restarted.logout(); assertNull(vault.value)
        assertEquals(3600,restarted.login("account@example.com","123456").freeTime!!.seconds)
        assertFalse(restarted.profile!!.isDemo)
    }
}
