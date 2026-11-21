package com.prettylisavpn.android

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.Uri
import android.net.VpnService
import android.os.Bundle
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import com.google.gson.Gson
import com.prettylisavpn.android.vpn.ManagedRuntime
import com.wireguard.crypto.KeyPair
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test

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
        ActivityScenario.launch(MainActivity::class.java).use {
            val uplink = requireNotNull(connectivity.activeNetwork) { "No physical Android uplink" }
            assertTrue("The fixture must use Wi-Fi", connectivity.getNetworkCapabilities(uplink)
                ?.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) == true)
            // A separate hostname checks the fixture without warming the direct site's DNS cache.
            val baseline = fetch(context, "uplink.prettylisa.test")
            assertTrue("The Android Wi-Fi fixture must answer HTTP: $baseline", proof(baseline))
            assertNull("The disposable emulator must authorize VPN for the test APK", VpnService.prepare(context))
            try {
                runBlocking {
                    runtime.start(profile)
                    withTimeout(15_000) {
                        while (!ownsTun(connectivity)) delay(100)
                        while (!clientCall(context, "ready", null).getBoolean("ready")) delay(100)
                    }
                }
                val directReply = fetch(context, direct)
                assertTrue("The separate client must receive a FakeDNS address through VPN: ${details(directReply)}",
                    directReply.getBoolean("vpn") && directReply.getBoolean("fake"))
                assertTrue("Direct site should respond through the Android uplink: ${details(directReply)}", proof(directReply))
                val selectedReply = fetch(context, selected)
                assertTrue("FakeDNS must also answer for selected domains: ${details(selectedReply)}",
                    selectedReply.getBoolean("vpn") && selectedReply.getBoolean("fake"))
                assertTrue("A selected domain must not reach the physical fixture", !selectedReply.getBoolean("responded"))
            } finally {
                if (runtime.isOwned) runBlocking { runtime.stop() }
            }
        }
    }

    @Suppress("DEPRECATION")
    private fun ownsTun(connectivity: ConnectivityManager): Boolean = connectivity.allNetworks.any { network ->
        connectivity.getNetworkCapabilities(network)?.hasTransport(NetworkCapabilities.TRANSPORT_VPN) == true &&
            connectivity.getLinkProperties(network)?.linkAddresses?.any { it.address.hostAddress == "172.30.255.1" } == true
    }

    private fun fetch(context: Context, host: String): Bundle = clientCall(context, "fetch", host)

    private fun clientCall(context: Context, method: String, host: String?): Bundle = requireNotNull(context.contentResolver.call(
        Uri.parse("content://com.prettylisavpn.android.test.physical-dns"), method, host, null,
    ))

    private fun details(reply: Bundle): String =
        "vpn=${reply.getBoolean("vpn")}, fake=${reply.getBoolean("fake")}, error=${reply.getString("error")}"

    private fun proof(reply: Bundle): Boolean = reply.getBoolean("proof")
}
