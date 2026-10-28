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
            compose.activity.setContent { PrettyLisaTheme { LocalizedApp { LiveHome(model) } } }
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

    private fun screenshot(name: String) {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val folder = File(instrumentation.targetContext.getExternalFilesDir(null), "acceptance").apply { mkdirs() }
        assertTrue(UiDevice.getInstance(instrumentation).takeScreenshot(File(folder, "$name.png")))
    }
}
