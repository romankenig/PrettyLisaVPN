package com.prettylisavpn.android

import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.VpnService
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
import java.io.ByteArrayOutputStream
import java.io.DataOutputStream
import java.io.IOException
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.InetSocketAddress
import java.nio.ByteBuffer

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
            assertTrue("Android's Wi-Fi resolver must reach the fixture", uplink.getAllByName("uplink.prettylisa.test")
                .any { it.hostAddress == "10.0.2.2" })
            assertNull("The disposable emulator must authorize VPN for the test APK", VpnService.prepare(context))
            try {
                val vpn = runBlocking {
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
                assertTrue("Direct site should respond through the Android uplink",
                    fetch(vpn, direct, fakeAddress(vpn, direct)).contains("direct-split-dns-proof"))
                val selectedAddress = fakeAddress(vpn, selected)
                val selectedResponse = try { fetch(vpn, selected, selectedAddress) } catch (_: IOException) { "" }
                assertTrue("A selected domain must not reach the physical fixture", selectedResponse.isEmpty())
            } finally {
                if (runtime.isOwned) runBlocking { runtime.stop() }
            }
        }
    }

    private fun ownsTun(connectivity: ConnectivityManager, network: Network): Boolean =
        connectivity.getNetworkCapabilities(network)?.hasTransport(NetworkCapabilities.TRANSPORT_VPN) == true &&
            connectivity.getLinkProperties(network)?.linkAddresses?.any { it.address.hostAddress == "172.30.255.1" } == true

    private fun fetch(vpn: Network, host: String, fake: InetAddress): String {
        return vpn.socketFactory.createSocket().use { socket ->
            socket.soTimeout = 5_000
            socket.connect(InetSocketAddress(fake, 18_080), 5_000)
            socket.getOutputStream().write("GET /proof.txt HTTP/1.0\r\nHost: $host\r\n\r\n".toByteArray())
            socket.getInputStream().bufferedReader().readText()
        }
    }

    private fun fakeAddress(vpn: Network, host: String): InetAddress {
        val query = ByteArrayOutputStream().apply {
            DataOutputStream(this).apply {
                writeShort(0x506c) // Transaction ID.
                writeShort(0x0100) // Recursion desired.
                writeShort(1)
                writeShort(0)
                writeShort(0)
                writeShort(0)
                for (label in host.split('.')) {
                    writeByte(label.length)
                    writeBytes(label)
                }
                writeByte(0)
                writeShort(1) // A record.
                writeShort(1) // IN class.
            }
        }.toByteArray()
        // The VPN owner's Android name-service calls can use the physical DNS.
        // Bind the packet itself to the VPN so FakeDNS receives it through TUN.
        val response = DatagramSocket(null).use { socket ->
            vpn.bindSocket(socket)
            socket.soTimeout = 5_000
            socket.connect(InetSocketAddress("1.1.1.1", 53))
            socket.send(DatagramPacket(query, query.size))
            DatagramPacket(ByteArray(512), 512).also { socket.receive(it) }
        }
        val packet = ByteBuffer.wrap(response.data, 0, response.length)
        assertTrue("FakeDNS must answer the A query", packet.getShort(0) == 0x506c.toShort() && packet.getShort(6) == 1.toShort())
        packet.position(12)
        skipDnsName(packet)
        packet.position(packet.position() + 4)
        skipDnsName(packet)
        assertTrue("FakeDNS answer must be an IPv4 A record", packet.short == 1.toShort())
        packet.position(packet.position() + 6) // Class and TTL.
        assertTrue("FakeDNS A record must have four bytes", packet.short == 4.toShort())
        val address = ByteArray(4).also { packet.get(it) }
        assertTrue("Expected an address in the FakeDNS pool", (address[0].toInt() and 0xff) == 198 &&
            (address[1].toInt() and 0xfe) == 18)
        return InetAddress.getByAddress(address)
    }

    private fun skipDnsName(packet: ByteBuffer) {
        while (true) {
            val length = packet.get().toInt() and 0xff
            if (length == 0) return
            if (length and 0xc0 == 0xc0) {
                packet.get()
                return
            }
            packet.position(packet.position() + length)
        }
    }
}
