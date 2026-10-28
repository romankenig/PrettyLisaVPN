package com.prettylisavpn.android.auth

import com.google.gson.JsonParser
import org.junit.Assert.*
import org.junit.Test

class FreeTimeTest {
    @Test fun accountBalanceIncludesTimeReservedByOtherDevices() {
        val json = JsonParser.parseString("""{"entitlements":{"free_seconds_remaining":0,"free_seconds_usable":600,"free_running_sessions":2,"free_quota_resets_at":"2030-01-02T00:00:00Z"}}""").asJsonObject
        val value = requireNotNull(readFreeTime(json, 1000))
        assertEquals(540, value.remaining(31000))
        assertEquals(480, value.remaining(400000))
        assertEquals(600, value.remaining(0))
        assertEquals(600, value.copy(running = 0).remaining(400000))
    }
    @Test fun unknownAndMalformedBalanceNeverInventAnHour() {
        for (source in listOf("{}", """{"entitlements":{"free_seconds_usable":9999}}""", """{"entitlements":{"free_seconds_usable":null}}""")) {
            assertNull(readFreeTime(JsonParser.parseString(source).asJsonObject))
        }
    }
}
