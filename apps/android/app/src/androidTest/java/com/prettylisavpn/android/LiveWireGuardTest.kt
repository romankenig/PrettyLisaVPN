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

/** Explicit dispatch only, with an expiring disposable account. No VPN mocks. */
class LiveWireGuardTest {
    @Test fun realConnectionAndConfirmedDisconnect() {
        assumeTrue(InstrumentationRegistry.getArguments().getString("liveWireGuard") == "true")
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val device = UiDevice.getInstance(instrumentation)
        val credentials = instrumentation.uiAutomation.executeShellCommand("cat /data/local/tmp/pl-wg-credentials.json").use { descriptor ->
            FileInputStream(descriptor.fileDescriptor).use { JsonParser.parseString(it.readBytes().toString(Charsets.UTF_8)).asJsonObject }
        }
        val country = credentials.get("country").asString
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
                val deadline = SystemClock.elapsedRealtime() + 150_000
                while (SystemClock.elapsedRealtime() < deadline) {
                    val phase = requireNotNull(AndroidVpnHost.current()).status.value.phase
                    if (phase in setOf(VpnPhase.CONNECTED, VpnPhase.FAILED, VpnPhase.DISCONNECTED)) break
                    SystemClock.sleep(200)
                }
                val state = requireNotNull(AndroidVpnHost.current()).status.value
                val output = requireNotNull(context.getExternalFilesDir(null))
                device.takeScreenshot(File(output, "wireguard-proof.png"))
                File(output, "wireguard-proof.json").writeText(Gson().toJson(mapOf(
                    "source_sha" to BuildConfig.SOURCE_SHA, "version" to BuildConfig.VERSION_NAME,
                    "country" to country, "phase" to state.phase.name, "method" to state.method?.id,
                    "error" to state.error?.name, "wireguard" to AndroidVpnHost.current()?.wireguardDiagnostic())))
                assertEquals("Real tunnel-bound verification did not pass", VpnPhase.CONNECTED, state.phase)
                assertEquals("wireguard", state.method?.id)
            } finally {
                scenario.onActivity { AndroidVpnHost.current()?.disconnect() }
                val cleanupDeadline = SystemClock.elapsedRealtime() + 45_000
                while (AndroidVpnHost.current()?.status?.value?.phase == VpnPhase.DISCONNECTING && SystemClock.elapsedRealtime() < cleanupDeadline) SystemClock.sleep(200)
                assertEquals("Client cleanup was not confirmed", VpnPhase.DISCONNECTED, AndroidVpnHost.current()?.status?.value?.phase)
            }
        }
    }
}
