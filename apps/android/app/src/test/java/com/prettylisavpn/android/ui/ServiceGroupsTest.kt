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
            assertEquals(expected.reversed(), top.second)
            assertEquals(services.reversed(), all.second)
        }
    }
    @Test fun savedSelectionSortsFirstWithinEachBlock() {
        val groups = serviceGroups(services, "include", Locale.ENGLISH, setOf("1", "2", "13"))
        assertEquals(listOf("2", "1"), groups[0].second.take(2).map { it.id })
        assertEquals(listOf("13", "2", "1"), groups[1].second.take(3).map { it.id })
        assertEquals(services.take(10).map { it.id }.toSet(), groups[0].second.map { it.id }.toSet())
    }
}
