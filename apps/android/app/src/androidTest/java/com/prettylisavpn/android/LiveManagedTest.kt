package com.prettylisavpn.android

import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.SystemClock
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import com.google.gson.Gson
import com.google.gson.JsonParser
import com.prettylisavpn.android.auth.Credentials
import com.prettylisavpn.android.auth.KeystoreVault
import com.prettylisavpn.android.vpn.AndroidVpnHost
import com.prettylisavpn.android.vpn.DeviceMethodSelection
import com.prettylisavpn.android.vpn.VpnPhase
import com.prettylisavpn.android.vpn.connectionMethods
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File
import java.io.FileInputStream
import java.net.Proxy
import java.net.URL
import javax.net.ssl.HttpsURLConnection

/** Dispatch-only packaged TUN acceptance. Never persists credentials or traffic logs. */
class LiveManagedTest {
    @Test fun realMethodsAndConfirmedCleanup() {
        assumeTrue(InstrumentationRegistry.getArguments().getString("liveManaged") == "true")
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val device = UiDevice.getInstance(instrumentation)
        val credential = instrumentation.uiAutomation.executeShellCommand("cat /data/local/tmp/pl-managed-credentials.json").use { descriptor ->
            FileInputStream(descriptor.fileDescriptor).use { JsonParser.parseString(it.readBytes().toString(Charsets.UTF_8)).asJsonObject }
        }
        val country = credential.get("country").asString
        require(country in setOf("DE", "US"))
        val methods = credential.getAsJsonArray("methods").map { it.asString }
        require(methods.isNotEmpty() && methods.all { id -> connectionMethods.any { it.id == id } })
        KeystoreVault(context).write(Credentials(credential.get("sessionId").asString,
            credential.get("refreshToken").asString, credential.get("expiresAt").asString))
        val output = requireNotNull(context.getExternalFilesDir(null))
        val rows = mutableListOf<Map<String, Any?>>()
        fun save() = File(output, "managed-proof.json").writeText(Gson().toJson(mapOf(
            "source_sha" to BuildConfig.SOURCE_SHA, "version" to BuildConfig.VERSION_NAME,
            "country" to country, "results" to rows)))
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            var signedIn = false
            val authDeadline = SystemClock.elapsedRealtime() + 45_000
            while (!signedIn && SystemClock.elapsedRealtime() < authDeadline) {
                scenario.onActivity { signedIn = it.screenModel.state.value.data.signedIn }
                SystemClock.sleep(200)
            }
            assertTrue("Disposable account restoration failed", signedIn)
            for (method in methods) {
                val row = mutableMapOf<String, Any?>("method" to method, "connected" to false,
                    "tunnel_https" to false, "cleanup" to false)
                rows.add(row); save()
                try {
                    scenario.onActivity {
                        DeviceMethodSelection.get(context).apply {
                            all()
                            connectionMethods.filter { it.id != method }.forEach { toggle(it.id) }
                        }
                        requireNotNull(AndroidVpnHost.current()).connect(country)
                    }
                    val started = SystemClock.elapsedRealtime()
                    var observedStart = false
                    while (SystemClock.elapsedRealtime() - started < 180_000) {
                        device.findObject(By.res("android", "button1"))?.click()
                        val state = requireNotNull(AndroidVpnHost.current()).status.value
                        if (state.phase != VpnPhase.DISCONNECTED) observedStart = true
                        if (observedStart && state.phase in setOf(VpnPhase.CONNECTED, VpnPhase.FAILED, VpnPhase.DISCONNECTED)) break
                        SystemClock.sleep(250)
                    }
                    row["connect_seconds"] = (SystemClock.elapsedRealtime() - started) / 1_000
                    val host = requireNotNull(AndroidVpnHost.current())
                    row["phase"] = host.status.value.phase.name
                    row["error"] = host.status.value.error?.name
                    if (host.status.value.phase == VpnPhase.CONNECTED && host.status.value.method?.id == method) {
                        row["connected"] = true
                        val sustained = SystemClock.elapsedRealtime()
                        while (host.status.value.phase == VpnPhase.CONNECTED && SystemClock.elapsedRealtime() - sustained < 40_000) SystemClock.sleep(250)
                        row["sustained_seconds"] = (SystemClock.elapsedRealtime() - sustained) / 1_000
                        @Suppress("DEPRECATION")
                        val vpn = context.getSystemService(ConnectivityManager::class.java).let { manager ->
                            manager.allNetworks.firstOrNull { manager.getNetworkCapabilities(it)?.hasTransport(NetworkCapabilities.TRANSPORT_VPN) == true }
                        }
                        row["tunnel_https"] = host.status.value.phase == VpnPhase.CONNECTED && vpn != null && runCatching {
                            val connection = vpn.openConnection(URL("https://api.prettylisavpn.com/health"), Proxy.NO_PROXY) as HttpsURLConnection
                            try {
                                connection.connectTimeout = 8_000; connection.readTimeout = 8_000
                                connection.instanceFollowRedirects = false
                                connection.responseCode == 200 && connection.inputStream.bufferedReader().use { it.readText().contains("ok") }
                            } finally { connection.disconnect() }
                        }.getOrDefault(false)
                        device.takeScreenshot(File(output, "managed-$method.png"))
                    }
                } finally {
                    scenario.onActivity { AndroidVpnHost.current()?.disconnect() }
                    val cleanupDeadline = SystemClock.elapsedRealtime() + 45_000
                    while (AndroidVpnHost.current()?.status?.value?.phase == VpnPhase.DISCONNECTING && SystemClock.elapsedRealtime() < cleanupDeadline) SystemClock.sleep(200)
                    row["cleanup"] = AndroidVpnHost.current()?.status?.value?.phase == VpnPhase.DISCONNECTED
                    row["diagnostic"] = AndroidVpnHost.current()?.managedDiagnostic(method)
                    save()
                    assertEquals("Cleanup must finish before another method", true, row["cleanup"])
                }
            }
        }
        assertTrue("Every requested real method must pass; inspect redacted proof", rows.all {
            it["connected"] == true && it["tunnel_https"] == true && (it["sustained_seconds"] as? Long ?: 0) >= 40
        })
    }
}
