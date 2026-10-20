package com.prettylisavpn.android.ui

import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.*
import org.junit.Test

class PresentationTest {
    @Test fun defaultsToEnglishAndSuggestsRussianOnlyForRussia() {
        val writes = mutableListOf<String>()
        val preference = LanguagePreference(null, writes::add)
        assertEquals(AppLanguage.ENGLISH, preference.language.value)
        preference.suggest("RU"); assertEquals(AppLanguage.RUSSIAN, preference.language.value)
        preference.suggest("CN"); assertEquals(AppLanguage.ENGLISH, preference.language.value)
        preference.suggest(null); assertEquals(AppLanguage.ENGLISH, preference.language.value)
        assertTrue(writes.isEmpty())
    }
    @Test fun explicitChoiceWinsOverLateGeolocationAndSurvivesRestart() {
        var saved: String? = null
        val preference = LanguagePreference(null) { saved = it }
        preference.choose(AppLanguage.FRENCH)
        preference.suggest("RU")
        assertEquals(AppLanguage.FRENCH, preference.language.value)
        val restored = LanguagePreference(saved) { fail("Restoring must not write") }
        restored.suggest("RU")
        assertEquals(AppLanguage.FRENCH, restored.language.value)
    }
    @Test fun unavailablePreferenceStorageStillKeepsManualChoiceInMemory() {
        val preference = LanguagePreference("invalid") { error("Storage unavailable") }
        preference.choose(AppLanguage.GERMAN); preference.suggest("RU")
        assertEquals(AppLanguage.GERMAN, preference.language.value)
    }
    @Test fun languagesMatchWindowsAndAreSortedByEnglishName() {
        assertEquals(listOf("Chinese", "English", "French", "German", "Russian", "Spanish"), AppLanguage.entries.map { it.english })
        assertEquals(6, AppLanguage.entries.map { it.code }.toSet().size)
    }
    @Test fun publicMetadataUsesActualVersionAndCountryWithoutCredentials() = runBlocking {
        MockWebServer().use { server ->
            server.enqueue(MockResponse().setBody("""{"application_version":"0.10.0","environment":"development"}"""))
            server.enqueue(MockResponse().setBody("""{"success":true,"country_code":"RU"}"""))
            val metadata = PublicMetadata(server.url("/version").toString(), server.url("/country").toString())
            assertEquals("0.10.0", metadata.version()); assertEquals("RU", metadata.country())
            repeat(2) {
                val request = server.takeRequest()
                assertEquals("GET", request.method)
                assertNull(request.getHeader("Authorization")); assertNull(request.getHeader("Cookie"))
                assertEquals(0L, request.bodySize)
            }
        }
    }
    @Test fun invalidFailedAndOversizedMetadataFailClosed() = runBlocking {
        MockWebServer().use { server ->
            val metadata = PublicMetadata(server.url("/version").toString(), server.url("/country").toString())
            for (body in listOf("{}", """{"application_version":{}}""", """{"application_version":"not-a-version"}""", "x".repeat(16_385))) {
                server.enqueue(MockResponse().setBody(body)); assertNull(metadata.version())
            }
            server.enqueue(MockResponse().setResponseCode(503)); assertNull(metadata.version())
            server.enqueue(MockResponse().setBody("""{"success":false,"country_code":"RU"}""")); assertNull(metadata.country())
            server.enqueue(MockResponse().setBody("""{"success":true,"country_code":{}}""")); assertNull(metadata.country())
        }
    }
}
