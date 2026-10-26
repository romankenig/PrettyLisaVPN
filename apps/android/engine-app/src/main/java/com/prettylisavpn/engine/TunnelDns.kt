package com.prettylisavpn.engine

import android.net.Network
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.UnknownHostException
import java.security.SecureRandom

/** Fixed canary only, no system DNS cache/fallback and no browsing query logging. */
internal object TunnelDns {
    const val HOST = "connectivitycheck.gstatic.com"
    private val random = SecureRandom()
    internal fun query(id: Int): ByteArray {
        val bytes = java.io.ByteArrayOutputStream()
        fun word(value: Int) { bytes.write(value ushr 8); bytes.write(value and 255) }
        word(id); word(0x0100); word(1); word(0); word(0); word(0)
        HOST.split('.').forEach { label -> bytes.write(label.length); bytes.write(label.toByteArray(Charsets.US_ASCII)) }
        bytes.write(0); word(1); word(1)
        return bytes.toByteArray()
    }
    internal fun answers(response: ByteArray, request: ByteArray): List<InetAddress> {
        fun word(offset: Int): Int { require(offset >= 0 && offset + 1 < response.size); return ((response[offset].toInt() and 255) shl 8) or (response[offset + 1].toInt() and 255) }
        require(response.size >= request.size && response[0] == request[0] && response[1] == request[1])
        require(word(2) and 0xfa0f == 0x8000 && word(4) == 1) // response, standard opcode, untruncated, no error
        require(response.copyOfRange(12, request.size).contentEquals(request.copyOfRange(12, request.size)))
        val count = word(6).also { require(it in 1..32) }
        var offset = request.size
        val result = mutableListOf<InetAddress>()
        repeat(count) {
            var labels = 0
            while (true) {
                require(offset < response.size && labels++ < 128)
                val length = response[offset++].toInt() and 255
                if (length == 0) break
                if (length and 0xc0 == 0xc0) { require(offset < response.size); offset++; break }
                require(length <= 63 && offset + length <= response.size); offset += length
            }
            val type = word(offset); val clazz = word(offset + 2); val length = word(offset + 8)
            offset += 10; require(offset + length <= response.size)
            if (type == 1 && clazz == 1 && length == 4) {
                val address = InetAddress.getByAddress(response.copyOfRange(offset, offset + 4))
                require(!address.isAnyLocalAddress && !address.isLoopbackAddress && !address.isLinkLocalAddress && !address.isSiteLocalAddress && !address.isMulticastAddress)
                result += address
            }
            offset += length
        }
        require(result.isNotEmpty())
        return result.distinct()
    }
    fun resolve(network: Network): List<InetAddress> = try {
        DatagramSocket().use { socket ->
            network.bindSocket(socket) // NEVER protect this socket; it must traverse our TUN.
            socket.soTimeout = 4_000
            socket.connect(InetAddress.getByAddress(byteArrayOf(1,1,1,1)),53)
            val request = query(random.nextInt(65536))
            socket.send(DatagramPacket(request,request.size))
            val reply = DatagramPacket(ByteArray(4096),4096)
            socket.receive(reply)
            answers(reply.data.copyOf(reply.length),request)
        }
    } catch (_: Exception) { throw UnknownHostException("VPN_DNS_FAILED") }
}
