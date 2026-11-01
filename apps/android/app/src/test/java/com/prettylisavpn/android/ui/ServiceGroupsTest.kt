package com.prettylisavpn.android.ui

import com.prettylisavpn.android.vpn.TrafficService
import java.util.Locale
import org.junit.Assert.*
import org.junit.Test

class ServiceGroupsTest {
    private val services = (1..24).map { index ->
        TrafficService("$index", "service-$index", "Service ${('Z'.code - index).toChar()}", "website", listOf("example.com"),
            category = if (index <= 12) "popular" else "whitelist", popularity_rank = index)
    }
    @Test fun recommendationsDependOnModeAndLanguageButAllAlwaysContainsEveryService() {
        for (language in listOf("en", "ru", "de")) for (mode in listOf("include", "exclude")) {
            val (top, all) = serviceGroups(services, mode, Locale.forLanguageTag(language))
            val expected = if (language == "ru" && mode == "exclude") services.drop(12).take(10) else services.take(10)
            assertEquals(expected, top.second)
            assertEquals(services.reversed(), all.second)
        }
    }
}
