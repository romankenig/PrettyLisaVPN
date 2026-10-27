package com.prettylisavpn.android.network

import com.prettylisavpn.android.auth.HttpAuthApi
import com.prettylisavpn.android.ui.PublicMetadata
import kotlinx.coroutines.runBlocking
import okhttp3.Dns
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Test
import org.junit.Assert.*
import java.net.InetAddress
import java.net.Socket
import java.net.ConnectException
import javax.net.SocketFactory

class RoutedHttpClientTest {
    @After fun reset() { HttpRoutes.default() }

    @Test fun routeChangeDiscardsOldSocketsAndRestoresDefaultAfterDisconnect() {
        MockWebServer().use { server ->
            val base = OkHttpClient.Builder().retryOnConnectionFailure(false).followRedirects(false).build()
            val routed = RoutedHttpClient(base)
            fun request() {
                server.enqueue(MockResponse().setBody("ok"))
                routed.current().newCall(Request.Builder().url(server.url("/fixed-probe")).build()).execute().use {
                    assertEquals("ok", it.body!!.string())
                }
            }
            request(); assertEquals(0, server.takeRequest().sequenceNumber)
            request(); assertEquals(1, server.takeRequest().sequenceNumber)
            val before = routed.current()
            var lookups = 0
            HttpRoutes.vpn(SocketFactory.getDefault(), object : Dns {
                override fun lookup(hostname: String): List<InetAddress> { lookups++; return Dns.SYSTEM.lookup(hostname) }
            })
            request(); assertEquals(0, server.takeRequest().sequenceNumber)
            assertTrue(lookups > 0)
            assertNotSame(before.connectionPool, routed.current().connectionPool)
            assertFalse(routed.current().retryOnConnectionFailure)
            assertFalse(routed.current().followRedirects)
            val vpn = routed.current()
            HttpRoutes.default()
            request(); assertEquals(0, server.takeRequest().sequenceNumber)
            assertNotSame(vpn.connectionPool, routed.current().connectionPool)
            assertSame(base.socketFactory, routed.current().socketFactory)
            assertSame(base.dns, routed.current().dns)
        }
    }

    @Test fun unavailableVpnCannotReuseWorkingDefaultConnection() {
        MockWebServer().use { server ->
            val routed = RoutedHttpClient(OkHttpClient.Builder().retryOnConnectionFailure(false).build())
            val request = Request.Builder().url(server.url("/fixed-probe")).build()
            server.enqueue(MockResponse().setBody("ok"))
            routed.current().newCall(request).execute().use { assertEquals("ok", it.body!!.string()) }
            HttpRoutes.vpn(object : SocketFactory() {
                override fun createSocket(): Socket = throw ConnectException("test route unavailable")
                override fun createSocket(h: String, p: Int): Socket = createSocket()
                override fun createSocket(h: String, p: Int, l: InetAddress, lp: Int): Socket = createSocket()
                override fun createSocket(h: InetAddress, p: Int): Socket = createSocket()
                override fun createSocket(h: InetAddress, p: Int, l: InetAddress, lp: Int): Socket = createSocket()
            }, Dns.SYSTEM)
            try { routed.current().newCall(request).execute().close(); fail("Must not use pre-VPN socket") }
            catch (_: ConnectException) { }
            assertEquals(1, server.requestCount)
        }
    }

    @Test fun authenticatedApiAndPublicNoticeBothFollowTheVpnRoute() = runBlocking {
        MockWebServer().use { server ->
            val http = HttpAuthApi(server.url("/").toString(), true)
            val metadata = PublicMetadata(server.url("/version").toString(), server.url("/location").toString())
            suspend fun round() {
                server.enqueue(MockResponse().setBody("{}"))
                http.request("vpn/wireguard/sessions/test/heartbeat", "POST", "{}".toRequestBody(), "fixture-bearer")
                assertEquals("Bearer fixture-bearer", server.takeRequest().getHeader("Authorization"))
                server.enqueue(MockResponse().setBody("{}")); assertTrue(metadata.reachable())
                assertNull(server.takeRequest().getHeader("Authorization"))
            }
            round()
            var lookups = 0
            HttpRoutes.vpn(SocketFactory.getDefault(), object : Dns {
                override fun lookup(hostname: String): List<InetAddress> { lookups++; return Dns.SYSTEM.lookup(hostname) }
            })
            round()
            assertEquals(2, lookups)
        }
    }
}
