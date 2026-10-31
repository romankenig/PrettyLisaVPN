package com.prettylisavpn.android.vpn

import org.junit.Assert.*
import org.junit.Test
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.flow.MutableStateFlow

class TrafficPolicyTest {
    @Test fun categoriesRetainLegacySavedListsAndAcceptWhitelist() {
        val legacy = """{"mode":"include","include":{"services":[{"id":"0bd811da-f080-4f25-887a-67bf534ac2c6","slug":"youtube","name":"YouTube","icon":"youtube","domains":["youtube.com"]}],"masks":["ifconfig.me"]},"exclude":{"services":[],"masks":["example.com"]}}"""
        val saved = TrafficPreference({ legacy }).current()
        assertEquals(listOf("ifconfig.me", "youtube.com"), saved.policy().domains)
        assertEquals(listOf("example.com"), saved.copy(mode = "exclude").policy().domains)
        assertEquals("whitelist", validateTrafficServices(listOf(saved.include.services.single().copy(category = "whitelist"))).single().category)
        assertTrue(runCatching { validateTrafficServices(listOf(saved.include.services.single().copy(category = "unknown"))) }.isFailure)
    }
    @Test fun applyingRulesWaitsForCleanupAndNeverReconnects() = runBlocking {
        for (phase in listOf(VpnPhase.CONNECTING, VpnPhase.CONNECTED)) {
            val state = MutableStateFlow(VpnStatus(phase))
            var stops = 0
            val vpn = object : VpnActions {
                override val status = state
                override fun connect(country: String) { error("Unexpected reconnect") }
                override fun disconnect() { stops++; state.value = VpnStatus(VpnPhase.DISCONNECTING) }
            }
            val store = TrafficPreference()
            val operation = launch(start = CoroutineStart.UNDISPATCHED) { applyTrafficSelection(TrafficSelection("include"), store, vpn) }
            assertEquals(1, stops)
            assertEquals("all", store.current().mode)
            state.value = VpnStatus(VpnPhase.DISCONNECTED)
            operation.join()
            assertEquals("include", store.current().mode)
        }
    }
    @Test fun failedCleanupKeepsPreviousRules() = runBlocking {
        val state = MutableStateFlow(VpnStatus(VpnPhase.CONNECTED))
        val vpn = object : VpnActions {
            override val status = state
            override fun connect(country: String) { error("Unexpected reconnect") }
            override fun disconnect() { state.value = VpnStatus(VpnPhase.FAILED, VpnError.CLEANUP) }
        }
        val store = TrafficPreference()
        assertTrue(runCatching { applyTrafficSelection(TrafficSelection("include"), store, vpn) }.isFailure)
        assertEquals("all", store.current().mode)
    }
    @Test fun explicitSaveRefreshesOnlySelectedPresetsAndRetainsOfflineChoices() {
        val old = TrafficService("0bd811da-f080-4f25-887a-67bf534ac2c6", "youtube", "YouTube", "youtube", listOf("youtube.com"))
        val updated = old.copy(domains = listOf("youtube.com", "*.googlevideo.com"))
        val value = TrafficSelection(include = TrafficList(services = listOf(old), masks = listOf("manual.example.com")))
        assertEquals(listOf(old), value.refreshServices(emptyList()).include.services)
        assertEquals(listOf(updated), value.refreshServices(listOf(updated)).include.services)
        assertEquals(listOf(old), value.include.services)
        assertEquals(TrafficList(), value.refreshServices(listOf(updated)).exclude)
        assertEquals(listOf("manual.example.com"), value.refreshServices(listOf(updated)).include.masks)
    }
    @Test fun masksAreExactOrWildcardAndNormalized() {
        assertEquals("youtube.com", normalizeTrafficMask(" YouTube.com "))
        assertEquals("*.youtube.com", normalizeTrafficMask("*.YouTube.com"))
        assertEquals("xn--e1afmkfd.xn--p1ai", normalizeTrafficMask("пример.рф"))
        listOf("https://a.com", "a.com/path", "a.com:443", "a.*.com", "*.com", "127.0.0.1", "a..com", "-a.com").forEach { mask ->
            assertTrue(mask, runCatching { normalizeTrafficMask(mask) }.isFailure)
        }
    }
    @Test fun listsRemainIndependentAcrossRestartAndModeChange() {
        var disk: String? = null
        val store = TrafficPreference({ disk }, { disk = it })
        val selection = TrafficSelection("include", TrafficList(masks = listOf("youtube.com", "*.youtube.com")), TrafficList(masks = listOf("instagram.com")))
        store.save(selection)
        assertEquals(selection, TrafficPreference({ disk }).current())
        assertEquals(listOf("youtube.com", "*.youtube.com"), selection.policy().domains)
        assertEquals(listOf("instagram.com"), selection.copy(mode = "exclude").policy().domains)
        assertTrue(selection.copy(mode = "all").policy().domains.isEmpty())
        assertTrue(runCatching { TrafficSelection("include", TrafficList(masks = (1..257).map { "s$it.example.com" })).policy() }.isFailure)
    }
}
