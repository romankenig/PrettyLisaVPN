package com.prettylisavpn.android.ui

import com.prettylisavpn.android.vpn.VpnEgress
import org.junit.Assert.*
import org.junit.Test

class SecondaryLocationTest {
    private val egress = VpnEgress("session-nl", "NL", "198.51.100.42")
    private val direct = PublicLocation("203.0.113.7", "RU", "Moscow")

    @Test fun failedLookupsUseTheCorrectRouteIncludingAutopilotAllocation() {
        val vpn = secondaryLocation("include", null, egress, direct)
        assertEquals(PublicLocation("198.51.100.42", "NL", null), vpn.value)
        assertTrue(vpn.expected)
        val excluded = secondaryLocation("exclude", null, egress, direct)
        assertEquals(direct, excluded.value)
        assertTrue(excluded.expected)
        assertNull(secondaryLocation("exclude", null, egress, null).value)
        assertNull(secondaryLocation("include", null, null, direct).value)
        assertNull(secondaryLocation("all", null, egress, direct).value)
    }

    @Test fun realObservationOverridesExpectedCountryAndIp() {
        val actual = PublicLocation("198.51.100.99", "DE", "Frankfurt")
        for (mode in listOf("include", "exclude")) {
            assertEquals(LocationDisplay(actual), secondaryLocation(mode, actual, egress, direct))
        }
    }

    @Test fun ipOnlyResultGetsExpectedCountryWithoutInventingACity() {
        val actual = PublicLocation("198.51.100.99", null, null)
        val result = secondaryLocation("include", actual, egress, direct)
        assertEquals(PublicLocation("198.51.100.99", "NL", null), result.value)
        assertTrue(result.expected)
        assertNull(secondaryLocation("exclude", actual, egress, direct).value?.city)
    }

    @Test fun countryRemainsUsefulWithoutAnExpectedIp() {
        assertEquals(PublicLocation(null, "NL", null),
            secondaryLocation("include", null, egress.copy(ip = null), direct).value)
    }

    @Test fun newSessionReplacesOldExpectedData() {
        val next = VpnEgress("session-de", "DE", "198.51.100.77")
        val result = secondaryLocation("include", null, next, direct)
        assertEquals(PublicLocation("198.51.100.77", "DE", null), result.value)
        assertNull(secondaryLocation("include", null, null, direct).value)
    }
}
