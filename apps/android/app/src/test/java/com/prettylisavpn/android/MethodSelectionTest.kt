package com.prettylisavpn.android

import com.prettylisavpn.android.vpn.*
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test

class MethodSelectionTest {
    @Test fun subsetSurvivesRestartAndCannotBecomeEmpty() {
        var saved: Set<String>? = null
        val selection = MethodSelection({ saved }, { saved = it })
        assertNull(selection.current())
        connectionMethods.filter { it.id != "wireguard" }.forEach { selection.toggle(it.id) }
        selection.toggle("unknown"); selection.toggle("wireguard")
        assertEquals(setOf("wireguard"), selection.current())
        val restored = MethodSelection({ saved }, { saved = it })
        assertEquals(setOf("wireguard"), restored.current())
        restored.all(); assertNull(MethodSelection({ saved }).current())
    }
    @Test fun invalidAndUnavailableStorageUseAllMethods() {
        assertNull(MethodSelection({ setOf("removed") }).current())
        assertNull(MethodSelection({ emptySet() }).current())
        val selection = MethodSelection({ error("unavailable") }, { error("unavailable") })
        selection.toggle("wireguard")
        assertFalse("wireguard" in selection.current().orEmpty())
    }
    @Test fun disabledPreferredMethodIsSkippedAndChangesApplyOnlyToNextAttempt() = runBlocking {
        var enabled = setOf("wireguard", "vmess"); val calls = mutableListOf<String>()
        val adapters = listOf("wireguard", "wireguard_relay", "vmess").map { id -> object : ConnectionAdapter {
            override val method = VpnMethod(id, id)
            override suspend fun connect(country: String): ConnectionResult {
                calls += id; enabled = setOf("wireguard_relay"); return ConnectionResult.Failed
            }
            override suspend fun disconnect() { calls += "stop-$id" }
        } }
        val preference = MethodPreference(); preference.remember("wireguard_relay")
        val controller = VpnController({ "owner" }, this, adapters, preference, enabledMethods = { enabled })
        controller.connect("DE"); yield()
        assertEquals(listOf("wireguard", "stop-wireguard", "vmess", "stop-vmess"), calls)
        calls.clear(); controller.connect("DE"); yield()
        assertEquals(listOf("wireguard_relay", "stop-wireguard_relay"), calls)
    }
}
