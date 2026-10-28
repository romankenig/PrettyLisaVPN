package com.prettylisavpn.android.vpn

import com.google.gson.Gson
import com.prettylisavpn.android.auth.HttpAuthApi
import com.prettylisavpn.android.auth.SessionCoordinator
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import java.time.Instant
import java.util.UUID

data class WireGuardConfiguration(val address: String, val server_public_key: String, val endpoint: String,
    val dns: List<String>, val allowed_ips: List<String>, val mtu: Int, val persistent_keepalive: Int,
    val expected_egress_ips: List<String>)
data class WireGuardLease(val id: String, val status: String, val country: String, val expires_at: String,
    val heartbeat_seconds: Int, val configuration: WireGuardConfiguration?,
    val heartbeat_required: Boolean? = null)

class WireGuardApi(private val http: HttpAuthApi, private val sessions: SessionCoordinator) {
    private val gson = Gson()
    private val path = "vpn/wireguard/sessions"
    private suspend fun call(suffix: String = "", method: String = "GET", body: Map<String,String>? = null, request: String? = null): WireGuardLease? =
        sessions.request { token ->
            val json = http.request(path + suffix, method,
                if (method == "POST") gson.toJson(body ?: emptyMap<String,String>()).toRequestBody("application/json".toMediaType()) else null,
                token, headers = request?.let { mapOf("Idempotency-Key" to it) } ?: emptyMap())
            if (json.isJsonNull) null else gson.fromJson(json, WireGuardLease::class.java).also {
                UUID.fromString(it.id); Instant.parse(it.expires_at)
                require(it.status in setOf("PROVISIONING", "READY", "REVOKING", "CLOSED"))
                require(it.heartbeat_seconds == 30)
            }
        }
    suspend fun connect(country: String, publicKey: String, request: String): WireGuardLease =
        requireNotNull(call(method = "POST", body = mapOf("country" to country, "public_key" to publicKey), request = request))
    suspend fun current() = call("/current")
    suspend fun get(id: String) = requireNotNull(call("/${UUID.fromString(id)}"))
    suspend fun heartbeat(id: String) = requireNotNull(call("/${UUID.fromString(id)}/heartbeat", "POST"))
    suspend fun revoke(id: String) = requireNotNull(call("/${UUID.fromString(id)}", "DELETE"))
}
