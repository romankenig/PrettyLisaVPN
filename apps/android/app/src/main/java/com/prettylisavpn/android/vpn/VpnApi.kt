package com.prettylisavpn.android.vpn

import com.google.gson.JsonObject
import com.google.gson.JsonParser
import com.prettylisavpn.android.auth.AuthFailure
import com.prettylisavpn.android.auth.HttpAuthApi
import com.prettylisavpn.android.auth.SessionCoordinator
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import java.time.Instant
import java.util.Base64
import java.util.UUID

/** No private material or bearer is exposed by these control-plane DTOs. */
data class VpnConfig(val endpoint: String, val port: Int, val serverKey: String, val address: String, val dns: List<String>, val mtu: Int = 1280)
data class VpnSession(val id: String, val country: String, val serverTime: Instant, val expiresAt: Instant?, val config: VpnConfig?)
interface VpnApi {
    suspend fun current(): VpnSession?
    suspend fun create(country: String, publicKey: String): VpnSession
    suspend fun delete(id: String)
}

class HttpVpnApi(private val http: HttpAuthApi, private val sessions: SessionCoordinator) : VpnApi {
    override suspend fun current(): VpnSession? = sessions.request { token ->
        val json = http.request("vpn/sessions/current", access = token, headers = mapOf("X-VPN-Candidates" to "1")).asJsonObject
        val value = json.get("session") ?: throw AuthFailure("invalid_response")
        if (value.isJsonNull) null else parseVpnSession(value.asJsonObject)
    }
    override suspend fun create(country: String, publicKey: String): VpnSession = sessions.request { token ->
        require(country == "AUTO" || country.matches(Regex("[A-Z]{2}")))
        val body = JsonObject().apply {
            addProperty("mode", if (country == "AUTO") "AUTO" else "COUNTRY")
            if (country != "AUTO") addProperty("country_code", country)
            addProperty("public_key", publicKey)
        }
        parseVpnSession(http.request("vpn/sessions", "POST", body.toString().toRequestBody("application/json".toMediaType()), token,
            headers = mapOf("X-VPN-Candidates" to "1")).asJsonObject)
    }
    override suspend fun delete(id: String) {
        UUID.fromString(id)
        try {
            sessions.request { token ->
                val json = http.request("vpn/sessions/$id", "DELETE", access = token).asJsonObject
                if (json.get("session_id")?.asString != id || json.get("status")?.asString !in setOf("DISCONNECTED", "EXPIRED", "FAILED")) throw AuthFailure("invalid_response")
            }
        } catch (failure: AuthFailure) { if (failure.code != "VPN_SESSION_NOT_FOUND") throw failure }
    }
}

internal fun ipv4(value: String): Boolean = value.split('.').let { p -> p.size == 4 && p.all { it.matches(Regex("0|[1-9][0-9]{0,2}")) && it.toInt() <= 255 } }
internal fun ipv4Cidr(value: String): Boolean = value.split('/').let { it.size == 2 && ipv4(it[0]) && it[1].toIntOrNull() in 0..32 }
internal fun publicKey(value: String): Boolean = runCatching { value.matches(Regex("[A-Za-z0-9+/]{43}=")) && Base64.getDecoder().decode(value).let { it.size == 32 && it.any { b -> b != 0.toByte() } } }.getOrDefault(false)

/** Preserve the ID even for an unsupported/malformed transport so DELETE can compensate.
 * Only the first ordered candidate is considered. Legacy NATIVE is deliberately unsupported.
 */
internal fun parseVpnSession(json: JsonObject): VpnSession = try {
    val id = json.get("session_id").asString.also { UUID.fromString(it) }
    require(json.get("status").asString == "ACTIVE")
    val country = json.get("country_code").asString.also { require(it.matches(Regex("[A-Z]{2}"))) }
    val time = Instant.parse(json.get("server_time").asString)
    val expiry = json.get("expires_at").let { if (it == null || it.isJsonNull) null else Instant.parse(it.asString) }
    val config = runCatching {
        val transport = json.getAsJsonObject("transport")
        val endpoint = transport.getAsJsonObject("endpoint")
        val ip = endpoint.get("ipv4").asString.also { require(ipv4(it) && it != "0.0.0.0" && !it.startsWith("127.")) }
        val port = endpoint.get("port").asInt.also { require(it in 1..65535) }
        val key = transport.get("server_public_key").asString.also { require(publicKey(it)) }
        val address = transport.get("client_address").asString.also { require(ipv4Cidr(it) && it.endsWith("/32")) }
        val dns = transport.getAsJsonArray("dns").map { it.asString }.also { require(it.size in 1..4 && it.all(::ipv4)) }
        // A single IPv4 default route makes GoBackend block the unconfigured IPv6 family.
        require(transport.getAsJsonArray("allowed_ips").map { it.asString } == listOf("0.0.0.0/0"))
        val c = json.getAsJsonArray("candidates").first().asJsonObject
        require(c.get("country").asString == country && c.get("port").asInt == port)
        require(c.get("protocol").asString == "WIREGUARD" && c.get("transport").asString == "UDP")
        require(c.get("encryption_mode").asString == "WIREGUARD" && c.get("obfuscation_mode").asString == "NONE")
        require(c.get("mtu").asInt == 1280 && c.get("dns_mode").asString == "VPN" && c.get("routing_mode").asString == "FULL_TUNNEL")
        require(c.get("obfuscation_version").let { it == null || it.isJsonNull })
        require(c.get("transport_parameters").let { it == null || it.isJsonNull || it.asJsonObject.size() == 0 })
        VpnConfig(ip, port, key, address, dns)
    }.getOrNull()
    VpnSession(id, country, time, expiry, config)
} catch (_: Exception) { throw AuthFailure("invalid_response") }

internal fun parseVpnSession(raw: String): VpnSession = parseVpnSession(JsonParser.parseString(raw).asJsonObject)
