package com.prettylisavpn.android

import com.prettylisavpn.android.vpn.*
import com.prettylisavpn.android.vpn.placeholders.placeholderAdapters
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test

class PlaceholderConnectionTest {
    @Test fun everyShippedAdapterWaitsThreeSecondsAndFailsInOrder() = runBlocking {
        val adapters = placeholderAdapters()
        assertEquals(listOf("wireguard", "amneziawg", "openvpn", "ipsec", "sstp", "softether", "openconnect", "shadowsocks", "shadowsocks2022", "vmess", "vless", "trojan", "ssh", "hysteria"), adapters.map { it.method.id })
        val called = mutableListOf<String>()
        val checked = adapters.map { adapter -> object : ConnectionAdapter by adapter {
            override suspend fun connect(country: String): ConnectionResult {
                assertEquals("DE", country)
                called += adapter.method.id
                val start = System.nanoTime()
                val result = adapter.connect(country)
                assertTrue("${adapter.method.id} returned early", System.nanoTime() - start >= 3_000_000_000L)
                assertEquals(ConnectionResult.Failed, result)
                return result
            }
        } }
        val controller = VpnController({ "account" }, this, checked)
        controller.connect("DE")
        withTimeout(65_000) { while (controller.status.value.phase != VpnPhase.FAILED) delay(10) }
        assertEquals(adapters.map { it.method.id }, called)
        assertEquals(VpnError.METHODS_EXHAUSTED, controller.status.value.error)
        assertEquals("hysteria", controller.status.value.method?.id)
    }

    @Test fun cancellationStopsTheActualTimerAndDoubleClicksDoNotDuplicateAttempts() = runBlocking {
        val adapter = placeholder("wireguard", "WireGuard")
        var calls = 0
        val first = object : ConnectionAdapter by adapter {
            override suspend fun connect(country: String): ConnectionResult { calls++; return adapter.connect(country) }
        }
        val next = object : ConnectionAdapter by adapter {
            override suspend fun connect(country: String): ConnectionResult { fail("next method must not run"); return ConnectionResult.Failed }
        }
        val controller = VpnController({ "account" }, this, listOf(first, next))
        controller.connect("DE"); controller.connect("DE"); yield()
        assertEquals(1, calls)
        withTimeout(500) { controller.beforeLogout() }
        assertEquals(VpnPhase.DISCONNECTED, controller.status.value.phase)
        controller.connect("US"); yield()
        assertEquals(2, calls)
        controller.beforeForget()
    }

    @Test fun verifiedAdapterStopsFallbackAndDisconnectsBeforeAnotherRun() = runBlocking {
        val events = mutableListOf<String>()
        fun adapter(id: String, result: ConnectionResult) = object : ConnectionAdapter {
            override val method = VpnMethod(id, id)
            override suspend fun connect(country: String): ConnectionResult { events += id; return result }
            override suspend fun disconnect() { events += "stop-$id" }
        }
        val controller = VpnController({ "account" }, this, listOf(adapter("first", ConnectionResult.Failed), adapter("second", ConnectionResult.Verified), adapter("third", ConnectionResult.Verified)))
        controller.connect("DE"); yield()
        assertEquals(VpnPhase.CONNECTED, controller.status.value.phase)
        assertEquals("second", controller.status.value.method?.id)
        assertEquals(listOf("first", "stop-first", "second"), events)
        controller.beforeLogout()
        assertEquals("stop-second", events.last())
    }
}
