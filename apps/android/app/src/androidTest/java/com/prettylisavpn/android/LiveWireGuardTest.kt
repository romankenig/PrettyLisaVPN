package com.prettylisavpn.android

import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import com.google.gson.JsonParser
import com.google.gson.Gson
import com.prettylisavpn.android.auth.Credentials
import com.prettylisavpn.android.auth.KeystoreVault
import com.prettylisavpn.android.vpn.AndroidVpnHost
import com.prettylisavpn.android.vpn.VpnPhase
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File
import java.io.FileInputStream
import android.os.SystemClock
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import com.prettylisavpn.android.ui.PublicMetadata
import kotlinx.coroutines.runBlocking
import java.net.URL
import java.net.Proxy
import javax.net.ssl.HttpsURLConnection

/** Explicit dispatch only, with an expiring disposable account. No VPN mocks. */
class LiveWireGuardTest {
    @Test fun realConnectionAndConfirmedDisconnect() {
        assumeTrue(InstrumentationRegistry.getArguments().getString("liveWireGuard") == "true")
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val device = UiDevice.getInstance(instrumentation)
        fun shell(command: String): String = instrumentation.uiAutomation.executeShellCommand(command).use { descriptor ->
            FileInputStream(descriptor.fileDescriptor).use { it.readBytes().toString(Charsets.UTF_8).trim() }
        }
        val credentials = instrumentation.uiAutomation.executeShellCommand("cat /data/local/tmp/pl-wg-credentials.json").use { descriptor ->
            FileInputStream(descriptor.fileDescriptor).use { JsonParser.parseString(it.readBytes().toString(Charsets.UTF_8)).asJsonObject }
        }
        val country = credentials.get("country").asString
        val expectedMethod = InstrumentationRegistry.getArguments().getString("expectedMethod") ?: "wireguard"
        require(expectedMethod in setOf("wireguard", "wireguard_relay"))
        val attempts = mutableListOf<String>()
        require(country in setOf("DE", "US"))
        KeystoreVault(context).write(Credentials(credentials.get("sessionId").asString,
            credentials.get("refreshToken").asString, credentials.get("expiresAt").asString))
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            try {
                val authDeadline = SystemClock.elapsedRealtime() + 45_000
                var signedIn = false
                while (!signedIn && SystemClock.elapsedRealtime() < authDeadline) {
                    scenario.onActivity { signedIn = it.screenModel.state.value.data.signedIn }
                    SystemClock.sleep(200)
                }
                assertTrue("Disposable account restoration failed", signedIn)
                scenario.onActivity { requireNotNull(AndroidVpnHost.current()).connect(country) }
                device.wait(Until.findObject(By.res("android", "button1")), 10_000)?.click()
                val deadline = SystemClock.elapsedRealtime() + 240_000
                while (SystemClock.elapsedRealtime() < deadline) {
                    val current = requireNotNull(AndroidVpnHost.current()).status.value
                    current.attempt?.method?.id?.let { if (attempts.lastOrNull() != it) attempts.add(it) }
                    val phase = current.phase
                    if (phase in setOf(VpnPhase.CONNECTED, VpnPhase.FAILED, VpnPhase.DISCONNECTED)) break
                    SystemClock.sleep(200)
                }
                val sustainedStart = SystemClock.elapsedRealtime()
                while (AndroidVpnHost.current()?.status?.value?.phase == VpnPhase.CONNECTED &&
                    SystemClock.elapsedRealtime() - sustainedStart < 120_000) SystemClock.sleep(200)
                val sustainedSeconds = (SystemClock.elapsedRealtime() - sustainedStart) / 1_000
                assertEquals(VpnPhase.CONNECTED, AndroidVpnHost.current()?.status?.value?.phase)
                val beforeIdleHeartbeats = requireNotNull(AndroidVpnHost.current()?.wireguardDiagnostic()).heartbeats
                assertTrue("Initial API renewals must work", beforeIdleHeartbeats >= 3)
                @Suppress("DEPRECATION")
                fun vpnNetwork() = context.getSystemService(ConnectivityManager::class.java).let { manager ->
                    manager.allNetworks.firstOrNull { manager.getNetworkCapabilities(it)?.hasTransport(NetworkCapabilities.TRANSPORT_VPN) == true }
                }
                val beforeIdleNetwork = requireNotNull(vpnNetwork())
                var idleSeconds = 0L
                var deepIdle = false
                try {
                    shell("dumpsys battery unplug")
                    device.sleep()
                    shell("cmd deviceidle force-idle deep")
                    deepIdle = shell("cmd deviceidle get deep") == "IDLE"
                    assertTrue("Device must actually enter deep Doze", deepIdle)
                    val idleStarted = SystemClock.elapsedRealtime()
                    SystemClock.sleep(300_000) // Exceeds both old 90s heartbeat and 180s node TTL.
                    idleSeconds = (SystemClock.elapsedRealtime() - idleStarted) / 1_000
                    assertEquals("Sleep must not tear down the VPN", VpnPhase.CONNECTED, AndroidVpnHost.current()?.status?.value?.phase)
                } finally {
                    shell("cmd deviceidle unforce")
                    shell("dumpsys battery reset")
                    device.wakeUp()
                    device.pressMenu()
                }
                val wakeDeadline = SystemClock.elapsedRealtime() + 100_000
                while (SystemClock.elapsedRealtime() < wakeDeadline &&
                    (AndroidVpnHost.current()?.wireguardDiagnostic()?.heartbeats ?: 0) <= beforeIdleHeartbeats) SystemClock.sleep(200)
                assertTrue("Heartbeat must reconcile after waking", requireNotNull(AndroidVpnHost.current()?.wireguardDiagnostic()).heartbeats > beforeIdleHeartbeats)
                val sameNetwork = vpnNetwork() == beforeIdleNetwork
                val state = requireNotNull(AndroidVpnHost.current()).status.value
                val publicApi = state.phase == VpnPhase.CONNECTED && runBlocking { PublicMetadata().reachable() }
                @Suppress("DEPRECATION")
                val vpn = context.getSystemService(ConnectivityManager::class.java).let { manager ->
                    manager.allNetworks.firstOrNull { manager.getNetworkCapabilities(it)?.hasTransport(NetworkCapabilities.TRANSPORT_VPN) == true }
                }
                val tunnelHttps = state.phase == VpnPhase.CONNECTED && vpn != null && runCatching {
                    val connection = vpn.openConnection(URL("https://api.prettylisavpn.com/health"), Proxy.NO_PROXY) as HttpsURLConnection
                    try {
                        connection.connectTimeout = 8_000; connection.readTimeout = 8_000
                        connection.instanceFollowRedirects = false
                        connection.responseCode == 200 && connection.inputStream.bufferedReader().use { it.readText().contains("ok") }
                    } finally { connection.disconnect() }
                }.getOrDefault(false)
                val noticeVisible = device.hasObject(By.text(context.getString(R.string.server_connection_lost)))
                val output = requireNotNull(context.getExternalFilesDir(null))
                device.takeScreenshot(File(output, "wireguard-proof.png"))
                File(output, "wireguard-proof.json").writeText(Gson().toJson(mapOf(
                    "source_sha" to BuildConfig.SOURCE_SHA, "version" to BuildConfig.VERSION_NAME,
                    "country" to country, "phase" to state.phase.name, "method" to state.method?.id,
                    "attempts" to attempts,
                    "sustained_seconds" to sustainedSeconds, "public_api_reachable" to publicApi,
                    "deep_idle_confirmed" to deepIdle, "idle_seconds" to idleSeconds,
                    "same_vpn_network" to sameNetwork,
                    "tunnel_https_rechecked" to tunnelHttps, "notice_visible" to noticeVisible,
                    "error" to state.error?.name, "wireguard" to AndroidVpnHost.current()?.wireguardDiagnostic())))
                assertEquals("Real tunnel-bound verification did not pass", VpnPhase.CONNECTED, state.phase)
                assertEquals(expectedMethod, state.method?.id)
                if (expectedMethod == "wireguard_relay") assertEquals(listOf("wireguard", "wireguard_relay"), attempts.take(2))
                assertTrue("Tunnel did not survive two minutes", sustainedSeconds >= 120)
                assertTrue("Tunnel must survive five minutes of deep Doze", deepIdle && idleSeconds >= 300)
                assertTrue("Wake-up must preserve the original VPN network", sameNetwork)
                assertTrue("At least three lease renewals must reach the API", requireNotNull(AndroidVpnHost.current()?.wireguardDiagnostic()).heartbeats >= 3)
                assertTrue("Public server notice probe must work over VPN", publicApi)
                assertTrue("HTTPS through the VPN must still work", tunnelHttps)
                assertFalse("App must not show a false connection-loss notice", noticeVisible)
            } finally {
                scenario.onActivity { AndroidVpnHost.current()?.disconnect() }
                val cleanupDeadline = SystemClock.elapsedRealtime() + 45_000
                while (AndroidVpnHost.current()?.status?.value?.phase == VpnPhase.DISCONNECTING && SystemClock.elapsedRealtime() < cleanupDeadline) SystemClock.sleep(200)
                assertEquals("Client cleanup was not confirmed", VpnPhase.DISCONNECTED, AndroidVpnHost.current()?.status?.value?.phase)
            }
        }
    }
}
