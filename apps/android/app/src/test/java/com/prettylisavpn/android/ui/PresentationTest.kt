package com.prettylisavpn.android.ui

import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.launch
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.*
import org.junit.Test

class PresentationTest {
    @Test fun runtimeVersionDisplaysOnlyValidatedReleaseCore() {
        for (version in listOf("0.10.0", "0.10.0-dev.39206276137+g69ab8d1d3d3c5680fc72bb23980776242606a104", "0.10.0-rc.1", "0.10.0+build.002")) {
            assertEquals("0.10.0", releaseVersion(version))
        }
        assertEquals("12.34.567", releaseVersion("12.34.567-beta+abc123"))
        for (version in listOf(null, "", "dev-69ab8d1", "0.10", "v0.10.0", "01.10.0", "0.10.0-01", "0.10.0+", "0.10.0-dev..2", "0.10.0 trailing", "9".repeat(300))) {
            assertNull(version, releaseVersion(version))
        }
    }
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
            server.enqueue(MockResponse().setBody("""{"application_version":"0.10.0-dev.39206276137+g69ab8d1d3d3c5680fc72bb23980776242606a104","environment":"development"}"""))
            server.enqueue(MockResponse().setBody("""{"success":true,"ip":"192.0.2.10","country_code":"RU"}"""))
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
    @Test fun serverReachabilityIsIndependentOfVersionFormatAndPublicLocation() = runBlocking {
        MockWebServer().use { server ->
            val metadata=PublicMetadata(server.url("/version").toString(),server.url("/location").toString())
            server.enqueue(MockResponse().setResponseCode(503));assertFalse(metadata.reachable())
            server.enqueue(MockResponse().setBody("{\"application_version\":\"future-format\"}"));assertTrue(metadata.reachable())
            repeat(2) { val request=server.takeRequest();assertEquals("/version",request.path);assertNull(request.getHeader("Authorization"));assertNull(request.getHeader("Cookie")) }
        }
    }
    @Test fun invalidFailedAndOversizedMetadataFailClosed() = runBlocking {
        MockWebServer().use { server ->
            val metadata = PublicMetadata(server.url("/version").toString(), server.url("/country").toString())
            for (body in listOf("{}", """{"application_version":{}}""", """{"application_version":["0.10.0"]}""", """{"application_version":10}""", """{"application_version":"not-a-version"}""", "x".repeat(16_385))) {
                server.enqueue(MockResponse().setBody(body)); assertNull(metadata.version())
            }
            server.enqueue(MockResponse().setResponseCode(503)); assertNull(metadata.version())
            server.enqueue(MockResponse().setBody("""{"success":false,"country_code":"RU"}""")); assertNull(metadata.country())
            server.enqueue(MockResponse().setBody("""{"success":true,"country_code":{}}""")); assertNull(metadata.country())
        }
    }
    @Test fun publicLocationValidatesEgressWithoutSendingIdentity() = runBlocking {
        MockWebServer().use { server ->
            val metadata=PublicMetadata(server.url("/version").toString(),server.url("/location").toString())
            server.enqueue(MockResponse().setBody("""{"success":true,"ip":"192.0.2.10","country_code":"DE","city":"Berlin"}"""))
            assertEquals(PublicLocation("192.0.2.10","DE","Berlin"),metadata.location())
            val request=server.takeRequest();assertNull(request.getHeader("Authorization"));assertNull(request.getHeader("Cookie"))
            for(ip in listOf("999.0.0.1","example.com","192.0.2.1/path")) {
                server.enqueue(MockResponse().setBody("""{"success":true,"ip":"$ip"}"""));assertNull(metadata.location());server.takeRequest()
            }
        }
    }
    @Test fun publicLocationFallsBackOnHttpDnsOrInvalidResponseAndStopsOnSuccess() = runBlocking {
        MockWebServer().use { primary -> MockWebServer().use { secondary ->
            val fallback = secondary.url("/json").toString()
            val metadata = PublicMetadata(primary.url("/version").toString(), primary.url("/location").toString(), fallback)
            for (response in listOf(MockResponse().setResponseCode(429), MockResponse().setBody("{\"success\":false}"), MockResponse().setBody("{\"success\":true,\"ip\":\"invalid\"}"))) {
                primary.enqueue(response)
                secondary.enqueue(MockResponse().setBody("""{"ip":"192.0.2.10","country":"NL","city":"Amsterdam","loc":"ignored"}"""))
                assertEquals(PublicLocation("192.0.2.10", "NL", "Amsterdam"), metadata.location())
                val request = secondary.takeRequest()
                assertNull(request.getHeader("Authorization")); assertNull(request.getHeader("Cookie"))
                assertEquals("/json", request.path)
            }
            primary.enqueue(MockResponse().setBody("""{"success":true,"ip":"192.0.2.20","country_code":"DE"}"""))
            assertEquals("DE", metadata.country()); assertEquals(3, secondary.requestCount)
            primary.enqueue(MockResponse().setResponseCode(503)); secondary.enqueue(MockResponse().setBody("""{"ip":"bad"}"""))
            assertNull(metadata.location())
            // .invalid is reserved and cannot resolve; fallback still uses the caller's route.
            secondary.enqueue(MockResponse().setBody("""{"ip":"2001:db8::1","country":"NL"}"""))
            assertEquals("NL", PublicMetadata(primary.url("/version").toString(), "https://unresolvable.invalid/", fallback).country())
        } }
    }
    @Test fun cancelledLocationDoesNotStartFallback() = runBlocking {
        MockWebServer().use { primary -> MockWebServer().use { secondary ->
            primary.enqueue(MockResponse().setBody("{\"success\":false}").setBodyDelay(300, java.util.concurrent.TimeUnit.MILLISECONDS))
            val job = launch(kotlinx.coroutines.Dispatchers.Default) {
                PublicMetadata(primary.url("/version").toString(), primary.url("/location").toString(), secondary.url("/json").toString()).location()
            }
            assertNotNull(primary.takeRequest(2, java.util.concurrent.TimeUnit.SECONDS))
            job.cancel(); job.join()
            assertEquals(1, primary.requestCount); assertEquals(0, secondary.requestCount)
        } }
    }
    @Test fun deviceDatesUseLocalCalendarAndAbsentDatesStayAbsent() {
        val raw="2026-10-20T23:41:10.625960Z"
        val utc=readableDate(raw,java.util.Locale.US,java.time.ZoneId.of("UTC"))!!
        val tokyo=readableDate(raw,java.util.Locale.US,java.time.ZoneId.of("Asia/Tokyo"))!!
        assertTrue(utc.contains("Oct 20, 2026"));assertTrue(tokyo.contains("Oct 21, 2026"))
        assertFalse(utc.contains("T23:"));assertNull(readableDate(null,java.util.Locale.US,java.time.ZoneId.of("UTC")))
    }

}
