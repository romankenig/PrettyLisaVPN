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
import com.prettylisavpn.android.vpn.DeviceTrafficSelection
import com.prettylisavpn.android.vpn.TrafficSelection
import com.prettylisavpn.android.vpn.TrafficList
import com.prettylisavpn.android.vpn.TrafficService
import com.prettylisavpn.android.ui.PublicMetadata
import kotlinx.coroutines.runBlocking
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
        val modes = credential.getAsJsonArray("routing_modes")?.map { it.asString } ?: listOf("all")
        require(modes.isNotEmpty() && modes.all { it in setOf("all", "include", "exclude") })
        // Fixed diagnostic origins only, no customer destinations or DNS logs.
        val origins = listOf("https://api.ipify.org", "https://ipv4.icanhazip.com", "https://ifconfig.me/ip")
        fun ip(origin: String, network: android.net.Network? = null): String {
            val connection = (network?.openConnection(URL(origin), Proxy.NO_PROXY)
                ?: URL(origin).openConnection(Proxy.NO_PROXY)) as HttpsURLConnection
            try {
                connection.connectTimeout = 15_000; connection.readTimeout = 15_000
                connection.instanceFollowRedirects = false; connection.useCaches = false
                check(connection.responseCode == 200)
                return connection.inputStream.bufferedReader().use { it.readText().trim() }.also {
                    check(it.matches(Regex("[0-9]{1,3}(\\.[0-9]{1,3}){3}")))
                }
            } finally { connection.disconnect() }
        }
        // A newly booted emulator can report boot_completed before physical DNS
        // is ready. Only retry this pre-VPN prerequisite; tunnel checks below
        // still require both distinct routes on each single connection attempt.
        val baseline = if (modes.any { it != "all" }) {
            var addresses: List<String>? = null
            val deadline = SystemClock.elapsedRealtime() + 60_000
            while (addresses == null && SystemClock.elapsedRealtime() < deadline) {
                addresses = runCatching { origins.map { ip(it) } }.getOrNull()
                if (addresses == null) SystemClock.sleep(2_000)
            }
            requireNotNull(addresses) { "Physical Internet/DNS unavailable before VPN" }
        } else emptyList()
        val exits = credential.getAsJsonArray("expected_egress_ips")?.map { it.asString } ?: emptyList()
        if (modes.any { it != "all" }) require(exits.isNotEmpty() && baseline.none { it in exits })
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
            for ((method, mode) in methods.flatMap { method -> modes.map { method to it } }) {
                val row = mutableMapOf<String, Any?>("method" to method, "routing_mode" to mode, "split_verified" to (mode == "all"), "connected" to false,
                    "tunnel_https" to false, "cleanup" to false)
                rows.add(row); save()
                try {
                    val idleDeadline = SystemClock.elapsedRealtime() + 45_000
                    while (AndroidVpnHost.current()?.status?.value?.phase != VpnPhase.DISCONNECTED && SystemClock.elapsedRealtime() < idleDeadline) SystemClock.sleep(200)
                    assertEquals("Session recovery must finish before connect", VpnPhase.DISCONNECTED, AndroidVpnHost.current()?.status?.value?.phase)
                    scenario.onActivity {
                        val masks = TrafficList(services = listOf(TrafficService(
                            "11111111-1111-4111-8111-111111111111", "telegram", "Telegram", "telegram",
                            listOf("telegram.org", "*.telegram.org"), ipv4_cidrs = listOf("149.154.160.0/20"))),
                            masks = listOf("api.ipify.org", "ifconfig.me"))
                        DeviceTrafficSelection.get(context).save(TrafficSelection(mode, masks, masks))
                        DeviceMethodSelection.get(context).apply {
                            all()
                            connectionMethods.filter { it.id != method }.forEach { toggle(it.id) }
                        }
                        requireNotNull(AndroidVpnHost.current()).connect(country)
                    }
                    val started = SystemClock.elapsedRealtime()
                    var observedStart = false
                    device.takeScreenshot(File(output, "managed-$method-$mode-start.png"))
                    while (SystemClock.elapsedRealtime() - started < 180_000) {
                        device.findObject(By.res("android", "button1"))?.click()
                        val state = requireNotNull(AndroidVpnHost.current()).status.value
                        if (state.phase != VpnPhase.DISCONNECTED) observedStart = true
                        row["phase"] = state.phase.name
                        row["diagnostic"] = AndroidVpnHost.current()?.managedDiagnostic(method)
                        save()
                        check(observedStart || SystemClock.elapsedRealtime() - started < 10_000) { "Connection did not start" }
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
                        if (mode != "all" && vpn != null) {
                            row["split_verified"] = runCatching {
                                val actual = origins.mapIndexed { index, origin ->
                                    try { ip(origin, vpn) } catch (error: Exception) { row["origin_${index}_error"] = error.javaClass.simpleName; throw error }
                                }
                                row["vpn_location_verified"] = runBlocking { PublicMetadata().vpnLocation()?.ip } == actual[2] && actual[2] in exits
                                check(row["vpn_location_verified"] == true)
                                val page = vpn.openConnection(URL("https://ifconfig.me/"), Proxy.NO_PROXY) as HttpsURLConnection
                                try {
                                    page.connectTimeout = 15_000; page.readTimeout = 15_000; page.instanceFollowRedirects = false
                                    page.setRequestProperty("User-Agent", "Mozilla/5.0 PrettyLisaVPN-Acceptance")
                                    row["ifconfig_page"] = page.responseCode == 200 && page.inputStream.bufferedReader().use { it.readText().contains(actual[2]) }
                                    check(row["ifconfig_page"] == true)
                                } finally { page.disconnect() }
                                actual.indices.all { index ->
                                    val shouldUseVpn = index == 2 || (index != 1) == (mode == "include")
                                    if (shouldUseVpn) actual[index] in exits else actual[index] == baseline[index]
                                }
                            }.getOrDefault(false)
                        }
                        device.takeScreenshot(File(output, "managed-$method-$mode.png"))
                    }
                } finally {
                    device.takeScreenshot(File(output, "managed-$method-$mode-final.png"))
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
            it["split_verified"] == true && it["connected"] == true && it["tunnel_https"] == true && (it["sustained_seconds"] as? Long ?: 0) >= 40
        })
    }
}
