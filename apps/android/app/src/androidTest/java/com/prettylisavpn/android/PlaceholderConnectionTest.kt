package com.prettylisavpn.android

import androidx.activity.compose.setContent
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.UiDevice
import com.prettylisavpn.android.ui.*
import com.prettylisavpn.android.data.*
import com.prettylisavpn.android.vpn.*
import com.prettylisavpn.android.vpn.placeholders.placeholderAdapters
import kotlinx.coroutines.*
import org.junit.*
import org.junit.Assert.*
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class PlaceholderConnectionTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()
    @Test fun resetControlAndHealthRecoveryUseTheConnectionExecutor() {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
        val events = mutableListOf<String>()
        var observedHealth = TunnelHealth.HEALTHY
        fun adapter(id: String) = object : ConnectionAdapter {
            override val method = VpnMethod(id, if (id == "wireguard") "WireGuard" else "VLESS")
            override suspend fun connect(country: String): ConnectionResult { events += "start:$id"; return ConnectionResult.Verified }
            override suspend fun disconnect() { events += "stop:$id" }
            override suspend fun health() = if (id == "wireguard") observedHealth else TunnelHealth.HEALTHY
        }
        val preference = MethodPreference(read = { "vless" })
        val controller = VpnController({ "test-owner" }, scope, listOf(adapter("wireguard"), adapter("vless")), preference,
            healthPolicy = ConnectionHealthPolicy(intervalMillis = 60_000, retryMillis = 2_000, recoveryBackoffMillis = 200))
        val model = ScreenModel(object : ScreenSource by FixtureSource(0) { override val vpn: VpnActions = controller })
        compose.runOnUiThread { compose.activity.setContent { PrettyLisaTheme { LocalizedApp { LiveHome(model) {} } } } }
        try {
            compose.onNodeWithTag("vpn-reset-methods").assertDoesNotExist()
            compose.onNodeWithTag("home-connect").performScrollTo().performClick()
            compose.waitUntil(5_000) { controller.status.value.method?.id == "vless" }
            compose.onNodeWithTag("vpn-reset-methods").performScrollTo().assertIsEnabled().performClick()
            compose.onNodeWithTag("vpn-reset-confirmation").assertExists()
            assertEquals(listOf("start:vless"), events)
            screenshot("vpn-reset-confirmation", settleWindow = true)
            compose.onNodeWithTag("vpn-reset-cancel").performClick()
            compose.onNodeWithTag("vpn-reset-confirmation").assertDoesNotExist()
            assertEquals(listOf("start:vless"), events)
            compose.onNodeWithTag("vpn-reset-methods").performClick()
            compose.onNodeWithTag("vpn-reset-confirm").performClick()
            compose.waitUntil(5_000) { controller.status.value.method?.id == "wireguard" }
            compose.onNodeWithTag("vpn-reset-confirmation").assertDoesNotExist()
            assertEquals(listOf("start:vless", "stop:vless", "start:wireguard"), events)
            screenshot("vpn-reset-methods", settleWindow = true)
            compose.runOnUiThread { observedHealth = TunnelHealth.NO_NETWORK; controller.transportLost("wireguard") }
            compose.waitUntil(5_000) { controller.status.value.phase == VpnPhase.WAITING_NETWORK }
            compose.onNodeWithTag("vpn-status").assertTextEquals("waiting for network…")
            screenshot("vpn-waiting-network")
            compose.runOnUiThread { observedHealth = TunnelHealth.HEALTHY; controller.transportLost("wireguard") }
            compose.waitUntil(5_000) { controller.status.value.phase == VpnPhase.CONNECTED }
            compose.runOnUiThread { observedHealth = TunnelHealth.UNREACHABLE; controller.transportLost("wireguard") }
            compose.waitUntil(5_000) { controller.status.value.phase == VpnPhase.CHECKING }
            compose.onNodeWithTag("vpn-status").assertTextEquals("checking connection…")
            screenshot("vpn-checking-connection")
            compose.waitUntil(10_000) { controller.status.value.phase == VpnPhase.CONNECTED && controller.status.value.method?.id == "vless" }
            assertEquals(listOf("start:vless", "stop:vless", "start:wireguard", "stop:wireguard", "start:vless"), events)
            screenshot("vpn-recovered-alternative")
            compose.onNodeWithTag("home-connect").performScrollTo().performClick()
            compose.waitUntil(5_000) { controller.status.value.phase == VpnPhase.DISCONNECTED }
            compose.onNodeWithTag("vpn-reset-methods").assertDoesNotExist()
        } finally { compose.runOnUiThread { controller.disconnect(); scope.cancel() } }
    }
    @Test fun shippedExecutorTriesAllMethodsAndCanBeCancelled() {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
        val visited = mutableListOf<String>()
        val adapters = placeholderAdapters()
        val durations = mutableListOf<Long>()
        val timedAdapters = adapters.map { adapter -> object : ConnectionAdapter by adapter {
            override suspend fun connect(country: String): ConnectionResult {
                // Measure the adapter itself, not delayed StateFlow delivery on a busy UI thread.
                // Handler-based coroutine delays use this same monotonic uptime clock.
                val began = android.os.SystemClock.uptimeMillis()
                try { return adapter.connect(country) }
                finally { durations += android.os.SystemClock.uptimeMillis() - began }
            }
        } }
        val controller = VpnController({ "test-owner" }, scope, timedAdapters)
        val model = ScreenModel(object : ScreenSource by FixtureSource(0) {
            override val vpn: VpnActions = controller
        })
        val start = android.os.SystemClock.elapsedRealtime()
        compose.runOnUiThread {
            scope.launch {
                controller.status.collect { status ->
                    if (status.phase == VpnPhase.CONNECTING) {
                        visited += status.attempt!!.method.id
                    }
                }
            }
            compose.activity.setContent { PrettyLisaTheme { LocalizedApp { LiveHome(model) {} } } }
        }
        try {
            compose.onNodeWithTag("home-connect").performScrollTo().performClick()
            compose.waitUntil(5_000) { controller.status.value.attempt?.method?.id == "wireguard" }
            compose.onNodeWithTag("vpn-attempt").assertTextContains("WireGuard", substring = true)
            compose.onNodeWithTag("vpn-duration-hint").assertExists()
            screenshot("placeholder-wireguard")
            compose.waitUntil(8_000) { controller.status.value.attempt?.method?.id == "amneziawg" }
            compose.onNodeWithTag("vpn-attempt").assertTextContains("AmneziaWG", substring = true)
            screenshot("placeholder-next-method")
            compose.waitUntil(65_000) { controller.status.value.phase == VpnPhase.FAILED }
            compose.runOnIdle {
                assertEquals(adapters.map { it.method.id }, visited)
                assertEquals(adapters.size, durations.size)
                assertTrue("Adapter durations: $durations", durations.all { it >= 3_000 })
                assertTrue(android.os.SystemClock.elapsedRealtime() - start >= 42_000)
                assertEquals(VpnError.METHODS_EXHAUSTED, controller.status.value.error)
            }
            compose.onNodeWithTag("vpn-method").assertDoesNotExist()
            compose.onNodeWithTag("vpn-duration-hint").assertDoesNotExist()
            compose.onNodeWithTag("vpn-error").performScrollTo().assertIsDisplayed()
            screenshot("placeholder-exhausted")
            compose.onNodeWithTag("home-connect").performScrollTo().performClick()
            compose.waitUntil(5_000) { controller.status.value.phase == VpnPhase.CONNECTING }
            compose.onNodeWithTag("home-connect").performClick()
            compose.waitUntil(2_000) { controller.status.value.phase == VpnPhase.DISCONNECTED }
            compose.onNodeWithTag("vpn-attempt").assertDoesNotExist()
            screenshot("placeholder-cancelled")
        } finally { compose.runOnUiThread { controller.disconnect(); scope.cancel() } }
    }

    private fun screenshot(name: String, settleWindow: Boolean = false) {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        if (settleWindow) {
            compose.waitForIdle()
            instrumentation.waitForIdleSync()
            // Dialog windows are composed separately; allow their opening/removal
            // to reach the display before UiAutomator captures the native frame.
            android.os.SystemClock.sleep(300)
        }
        val folder = File(instrumentation.targetContext.getExternalFilesDir(null), "acceptance").apply { mkdirs() }
        assertTrue(UiDevice.getInstance(instrumentation).takeScreenshot(File(folder, "$name.png")))
    }
}
