package com.prettylisavpn.android

import com.prettylisavpn.android.vpn.*
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test

class MethodPreferenceTest {
    private fun adapters(calls: MutableList<String>, works: Map<String, Boolean>) =
        listOf("wireguard", "wireguard_relay", "other").map { id -> object : ConnectionAdapter {
            override val method = VpnMethod(id, id)
            override suspend fun connect(country: String): ConnectionResult {
                calls += id
                return if (works[id] == true) ConnectionResult.Verified else ConnectionResult.Failed
            }
            override suspend fun disconnect() { calls += "stop-$id" }
        } }

    @Test fun verifiedChoiceSurvivesRecreationAndFailedPreferenceFallsBackOnce() = runBlocking {
        var saved: String? = null
        fun preference() = MethodPreference({ saved }, { saved = it })
        val calls = mutableListOf<String>()
        val works = mutableMapOf("wireguard_relay" to true)
        val first = VpnController({ "account" }, this, adapters(calls, works), preference())
        first.connect("DE"); yield()
        assertEquals(listOf("wireguard", "stop-wireguard", "wireguard_relay"), calls)
        assertEquals("wireguard_relay", saved)
        first.beforeLogout(); calls.clear()
        works["wireguard_relay"] = false; works["other"] = true
        val restarted = VpnController({ "account" }, this, adapters(calls, works), preference())
        restarted.connect("US"); yield()
        assertEquals(listOf("wireguard_relay", "stop-wireguard_relay", "wireguard", "stop-wireguard", "other"), calls)
        assertEquals("other", saved)
        restarted.beforeLogout()
    }

    @Test fun missingUnknownAndMalformedPreferencesKeepDefaultOrderAndFailuresAreNotSaved() = runBlocking {
        for (saved in listOf(null, "removed_method", "invalid stored value")) {
            val calls = mutableListOf<String>()
            var writes = 0
            val preference = MethodPreference({ saved }, { writes++ })
            val controller = VpnController({ "account" }, this, adapters(calls, emptyMap()), preference)
            controller.connect("DE"); yield()
            assertEquals(listOf("wireguard", "wireguard_relay", "other"), calls.filterNot { it.startsWith("stop-") })
            assertEquals(VpnPhase.FAILED, controller.status.value.phase)
            assertEquals(0, writes)
        }
    }

    @Test fun cancelledOrChangedOwnerMustNotSaveLateSuccess() = runBlocking {
        for (cancel in listOf(true, false)) {
            val release = CompletableDeferred<Unit>()
            var owner = "account"
            var writes = 0
            val adapter = object : ConnectionAdapter {
                override val method = VpnMethod("wireguard", "WireGuard")
                override suspend fun connect(country: String): ConnectionResult {
                    withContext(NonCancellable) { release.await() }
                    return ConnectionResult.Verified
                }
                override suspend fun disconnect() {}
            }
            val controller = VpnController({ owner }, this, listOf(adapter), MethodPreference(write = { writes++ }))
            controller.connect("DE"); yield()
            if (cancel) controller.disconnect() else owner = "another-account"
            release.complete(Unit); yield()
            controller.beforeLogout()
            assertEquals(0, writes)
            assertEquals(VpnPhase.DISCONNECTED, controller.status.value.phase)
        }
    }

    @Test fun storageFailureDoesNotBreakVerifiedConnection() = runBlocking {
        val preference = MethodPreference({ error("unavailable") }, { error("unavailable") })
        val controller = VpnController({ "account" }, this, adapters(mutableListOf(), mapOf("wireguard" to true)), preference)
        controller.connect("DE"); yield()
        assertEquals(VpnPhase.CONNECTED, controller.status.value.phase)
        assertEquals("wireguard", preference.current())
        controller.beforeLogout()
    }
}
