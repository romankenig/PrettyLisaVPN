package com.prettylisavpn.android

import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.VpnService
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import com.google.gson.Gson
import com.prettylisavpn.android.vpn.ManagedRuntime
import com.wireguard.crypto.KeyPair
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.IOException
import java.net.InetSocketAddress

/** Real Android TUN and protected sockets with DNS records available only on the emulator's uplink. */
class PhysicalSplitDnsTest {
    @Test fun splitUsesPhysicalNetworkDnsForDirectSitesOnly() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        assumeTrue(InstrumentationRegistry.getArguments().getString("physicalSplitDns") == "true")
        val context = instrumentation.targetContext
        val connectivity = context.getSystemService(ConnectivityManager::class.java)
        val runtime = ManagedRuntime(context) {}
        val direct = "direct.prettylisa.test"
        val selected = "selected.prettylisa.test"
        val profile = Gson().toJson(mapOf(
            "version" to 1,
            "session" to "ff48eb7c-e38b-4d55-9cbc-d648a692ce70",
            "country" to "DE",
            "method" to "WIREGUARD",
            "server" to "192.0.2.1",
            "port" to 51820,
            "address" to "10.65.3.2/32",
            "secret" to KeyPair().privateKey.toBase64(),
            "public_key" to KeyPair().publicKey.toBase64(),
            "routing" to mapOf("mode" to "include", "domains" to listOf(selected)),
        ))
        ActivityScenario.launch(MainActivity::class.java).use { activity ->
            VpnService.prepare(context)?.let { consent ->
                activity.onActivity { it.startActivity(consent) }
                val allow = UiDevice.getInstance(instrumentation)
                    .wait(Until.findObject(By.res("android", "button1")), 10_000)
                assertNotNull("VPN consent dialog did not open", allow)
                allow!!.click()
            }
            try {
                val vpn = runBlocking {
                    withTimeout(20_000) { while (VpnService.prepare(context) != null) delay(100) }
                    runtime.start(profile)
                    withTimeout(15_000) {
                        @Suppress("DEPRECATION")
                        var route = connectivity.allNetworks.firstOrNull { ownsTun(connectivity, it) }
                        while (route == null) {
                            delay(100)
                            @Suppress("DEPRECATION")
                            route = connectivity.allNetworks.firstOrNull { ownsTun(connectivity, it) }
                        }
                        requireNotNull(route)
                    }
                }
                assertTrue("Direct site should respond through the Android uplink", fetch(vpn, direct).contains("direct-split-dns-proof"))
                val selectedResponse = try { fetch(vpn, selected) } catch (_: IOException) { "" }
                assertTrue("A selected domain must not reach the physical fixture", selectedResponse.isEmpty())
            } finally {
                runBlocking { runtime.stop() }
            }
        }
    }

    private fun ownsTun(connectivity: ConnectivityManager, network: Network): Boolean =
        connectivity.getNetworkCapabilities(network)?.hasTransport(NetworkCapabilities.TRANSPORT_VPN) == true &&
            connectivity.getLinkProperties(network)?.linkAddresses?.any { it.address.hostAddress == "172.30.255.1" } == true

    private fun fetch(vpn: Network, host: String): String {
        val fake = vpn.getAllByName(host).first { address ->
            val bytes = address.address
            bytes.size == 4 && (bytes[0].toInt() and 0xff) == 198 && (bytes[1].toInt() and 0xfe) == 18
        }
        return vpn.socketFactory.createSocket().use { socket ->
            socket.soTimeout = 5_000
            socket.connect(InetSocketAddress(fake, 18_080), 5_000)
            socket.getOutputStream().write("GET /proof.txt HTTP/1.0\r\nHost: $host\r\n\r\n".toByteArray())
            socket.getInputStream().bufferedReader().readText()
        }
    }
}
