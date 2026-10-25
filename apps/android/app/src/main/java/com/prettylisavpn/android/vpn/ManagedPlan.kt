package com.prettylisavpn.android.vpn

import com.google.gson.JsonObject
import com.prettylisavpn.android.auth.AuthFailure
import java.time.Duration
import java.time.Instant
import java.util.UUID

/** Authenticated, bounded plan. A malformed plan is never silently truncated. */
internal fun parseManagedPlan(json: JsonObject, session: VpnSession): VpnSession = try {
    require(json.keySet() == setOf("profiles", "expires_at", "server_time"))
    val base = session.config ?: throw IllegalArgumentException()
    val profiles = json.getAsJsonArray("profiles")
    require(profiles.size() in 1..20 && session.country in setOf("DE", "US"))
    val candidates = profiles.map { entry ->
        val p = entry.asJsonObject
        val common = setOf("version", "session", "country", "method", "server", "port", "secret")
        val method = p.get("method").asString
        val transport = p.get("transport")?.asString
        VpnMethod.managed(method, transport) // Closed supported catalog.
        require(p.get("version").asString == "1" && p.get("session").asString == session.id)
        require(p.get("country").asString == session.country && p.get("server").asString == base.endpoint)
        val port = p.get("port").asString.also { require(it.matches(Regex("[1-9][0-9]{0,4}"))) }.toInt()
        require(port in 1024..65535)
        val secret = p.get("secret").asString
        require(secret.length in 16..128 && secret.none { it == '\u0000' || it == '\n' || it == '\r' })
        if (method in setOf("VLESS_REALITY", "VLESS_TLS", "VMESS_TLS")) require(UUID.fromString(secret).toString() == secret)
        if (method == "SHADOWSOCKS_2022") require(secret.split(':').let { it.size == 2 && it.all(::publicKey) })
        val reality = method == "VLESS_REALITY"
        val tls = method in setOf("VLESS_TLS", "VMESS_TLS", "TROJAN_TLS", "HYSTERIA2_TLS", "HYSTERIA2_SALAMANDER")
        val expected = common.toMutableSet()
        if (reality || tls) {
            expected += "server_name"
            require(p.get("server_name").asString.matches(Regex("[a-zA-Z0-9][a-zA-Z0-9.-]{1,251}[a-zA-Z0-9]")))
        }
        if (reality) {
            expected += setOf("public_key", "short_id")
            require(p.get("public_key").asString.matches(Regex("[A-Za-z0-9_-]{43}")))
            require(p.get("short_id").asString.matches(Regex("(?:[0-9a-f]{2}){1,8}")))
        }
        if (tls) {
            expected += "certificate_pin"
            require(p.get("certificate_pin").asString.matches(Regex("[0-9a-f]{64}")))
        }
        if (transport != null) {
            require(method in setOf("VLESS_TLS", "VMESS_TLS", "TROJAN_TLS"))
            expected += setOf("transport", "path")
            require(p.get("path").asString == if (transport == "grpc") "plvpn" else "/plvpn")
        }
        if (method == "HYSTERIA2_SALAMANDER") {
            expected += "obfs_secret"
            require(p.get("obfs_secret").asString.matches(Regex("[A-Za-z0-9+/]{43}=")))
        }
        require(p.keySet() == expected)
        base.copy(port = port, managed = ManagedProfile(p.toString()))
    }
    require(candidates.map { it.method }.distinct().size == candidates.size)
    require(candidates.map { it.port }.distinct().size == candidates.size)
    val time = Instant.parse(json.get("server_time").asString)
    val expiry = Instant.parse(json.get("expires_at").asString)
    require(expiry > time && Duration.between(time, expiry).seconds <= 1200)
    require(session.expiresAt == null || expiry <= session.expiresAt)
    // Preserve ALL supported WireGuard candidates and server order; do not replace them.
    val ordered = session.candidates + candidates
    session.copy(serverTime = time, expiresAt = expiry, config = ordered.first(), candidates = ordered)
} catch (_: Exception) { throw AuthFailure("invalid_response") }
