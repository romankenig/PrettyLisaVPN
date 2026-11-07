package com.prettylisavpn.android.vpn

import kotlinx.coroutines.*
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.SocketPolicy
import org.junit.Assert.*
import org.junit.Test
import java.util.concurrent.TimeUnit

class TunnelHealthProbeTest {
    private val ips = listOf("198.51.100.42")
    private fun probe(first: MockWebServer, second: MockWebServer) = TunnelHealthProbe(
        OkHttpClient.Builder().followRedirects(false).followSslRedirects(false).retryOnConnectionFailure(false).callTimeout(1, TimeUnit.SECONDS).build(),
        first.url("/ip").toString(), second.url("/version").toString())
    @Test fun expectedExitPassesAndRequestsNeverCarryCredentials() = runBlocking {
        MockWebServer().use { first -> MockWebServer().use { second ->
            first.enqueue(MockResponse().setBody("""{"ip_addr":"198.51.100.42"}"""))
            assertEquals(TunnelHealth.HEALTHY, probe(first, second).check(ips))
            val request = first.takeRequest(); assertNull(request.getHeader("Authorization")); assertNull(request.getHeader("Cookie"))
            assertEquals("no-store", request.getHeader("Cache-Control")); assertEquals(0, second.requestCount)
        } }
    }
    @Test fun wrongExitCannotBeHiddenByAWorkingApiFallback() = runBlocking {
        MockWebServer().use { first -> MockWebServer().use { second ->
            first.enqueue(MockResponse().setBody("""{"ip_addr":"192.0.2.1"}"""))
            assertEquals(TunnelHealth.UNREACHABLE, probe(first, second).check(ips)); assertEquals(0, second.requestCount)
        } }
    }
    @Test fun providerFailureOrMalformedMetadataCanUseTheSameTunnelApi() = runBlocking {
        MockWebServer().use { first -> MockWebServer().use { second ->
            for (response in listOf(MockResponse().setResponseCode(429), MockResponse().setBody("""{"ip_addr":"invalid"}"""), MockResponse().setBody("x".repeat(4097)))) {
                first.enqueue(response); second.enqueue(MockResponse().setBody("""{"application_version":"0.35.1"}"""))
                assertEquals(TunnelHealth.HEALTHY, probe(first, second).check(ips))
            }
        } }
    }
    @Test fun providerErrorsAreUnknownWhileTwoTransportFailuresAreUnreachable() = runBlocking {
        MockWebServer().use { first -> MockWebServer().use { second ->
            first.enqueue(MockResponse().setResponseCode(503)); second.enqueue(MockResponse().setResponseCode(503))
            assertEquals(TunnelHealth.UNKNOWN, probe(first, second).check(ips))
            first.enqueue(MockResponse().setSocketPolicy(SocketPolicy.DISCONNECT_AT_START))
            second.enqueue(MockResponse().setSocketPolicy(SocketPolicy.DISCONNECT_AT_START))
            assertEquals(TunnelHealth.UNREACHABLE, probe(first, second).check(ips))
        } }
    }
    @Test fun cancellationStopsLookupWithoutStartingAnotherProvider() = runBlocking {
        MockWebServer().use { first -> MockWebServer().use { second ->
            first.enqueue(MockResponse().setSocketPolicy(SocketPolicy.NO_RESPONSE))
            val job = launch { probe(first, second).check(ips) }
            withContext(Dispatchers.IO) { assertNotNull(first.takeRequest(2, TimeUnit.SECONDS)) }
            job.cancelAndJoin(); assertEquals(0, second.requestCount)
        } }
    }
}
