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
    @Test fun groupsAreDisjointAndSelectedServicesAlwaysComeFirst() {
        for (language in listOf("en", "ru", "de")) for (mode in listOf("include", "exclude")) {
            val chosen = setOf("1", "2", "13")
            val groups = serviceGroups(services, mode, Locale.forLanguageTag(language), chosen)
            assertEquals(listOf("selected", "top", "all"), groups.map { it.first })
            assertEquals(listOf("13", "2", "1"), groups[0].second.map { it.id })
            val top = if (language == "ru" && mode == "exclude") services.drop(12).take(10) else services.take(10)
            assertEquals(top.filter { it.id !in chosen }, groups[1].second)
            assertEquals(services.reversed().filter { it.id !in chosen && it !in top }, groups[2].second)
            val ids = groups.flatMap { it.second }.map { it.id }
            assertEquals(24, ids.size); assertEquals(24, ids.toSet().size)
        }
    }
    @Test fun selectingUpdatesOrderWithoutRefillingTopTen() {
        val before = serviceGroups(services, "include", Locale.ENGLISH)
        val after = serviceGroups(services + services.first(), "include", Locale.ENGLISH, setOf("1", "24"))
        assertTrue(before[0].second.isEmpty())
        assertEquals(listOf("24", "1"), after[0].second.map { it.id })
        assertEquals(9, after[1].second.size)
        assertEquals(24, after.flatMap { it.second }.size)
    }
}
