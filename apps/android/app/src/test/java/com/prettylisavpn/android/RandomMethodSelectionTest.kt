package com.prettylisavpn.android

import com.prettylisavpn.android.vpn.*
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test
import kotlin.random.Random

class RandomMethodSelectionTest {
    @Test fun randomOrderSurvivesRestartAndAlwaysChanges() {
        var saved: List<String>? = null
        val selection = MethodSelection({ saved }, { saved = it })
        val sizes = mutableSetOf<Int>()
        repeat(100) { seed ->
            val before = selection.current()
            selection.randomize(Random(seed))
            val next = requireNotNull(selection.current())
            assertTrue(next.isNotEmpty())
            assertEquals(next.size, next.toSet().size)
            assertTrue(next.all { id -> connectionMethods.any { it.id == id } })
            assertNotEquals(before, next)
            assertEquals(next, MethodSelection({ saved }).current())
            selection.randomize(Random(seed))
            assertNotEquals(next, selection.current())
            sizes += next.size
        }
        assertTrue(sizes.size > 1)
        selection.all(); assertNull(saved)
    }
    @Test fun manualChangesKeepRandomOrderAndAllRestoresDefault() {
        val selection = MethodSelection({ listOf("vmess", "wireguard", "vmess", "removed") })
        assertEquals(listOf("vmess", "wireguard"), selection.current())
        selection.toggle("sstp")
        assertEquals(listOf("vmess", "wireguard", "sstp"), selection.current())
        selection.toggle("wireguard")
        assertEquals(listOf("vmess", "sstp"), selection.current())
        selection.all(); assertNull(selection.current())
    }
    @Test fun baseOrderStillHonorsSuccessAndFailurePriority() = runBlocking {
        val calls = mutableListOf<String>()
        val adapters = listOf("wireguard", "vmess", "sstp").map { id -> object : ConnectionAdapter {
            override val method = VpnMethod(id, id)
            override suspend fun connect(country: String): ConnectionResult { calls += id; return ConnectionResult.Failed }
            override suspend fun disconnect() { calls += "stop-$id" }
        } }
        val preference = MethodPreference()
        preference.remember("vmess")
        val controller = VpnController({ "owner" }, this, adapters, preference, enabledMethods = { listOf("sstp", "wireguard", "vmess") })
        controller.connect("DE"); yield()
        assertEquals(listOf("vmess", "stop-vmess", "sstp", "stop-sstp", "wireguard", "stop-wireguard"), calls)
        calls.clear(); preference.failedAfterConnection("vmess")
        controller.connect("DE"); yield()
        assertEquals(listOf("sstp", "stop-sstp", "wireguard", "stop-wireguard", "vmess", "stop-vmess"), calls)
        assertEquals("vmess", preference.current())
    }
}
