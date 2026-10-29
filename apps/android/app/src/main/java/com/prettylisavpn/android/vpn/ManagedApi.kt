package com.prettylisavpn.android.vpn

import com.google.gson.Gson
import com.google.gson.JsonObject
import com.prettylisavpn.android.auth.HttpAuthApi
import com.prettylisavpn.android.auth.SessionCoordinator
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import java.time.Instant
import java.util.UUID

internal class ManagedConfiguration(val engine_profile: JsonObject, val expected_egress_ips: List<String>) {
    override fun toString() = "ManagedConfiguration([redacted])"
}
internal data class ManagedLease(val id: String, val status: String, val country: String,
    val method: String, val expires_at: String, val heartbeat_seconds: Int,
    val heartbeat_required: Boolean?, val configuration: ManagedConfiguration?)

internal class ManagedApi(private val http: HttpAuthApi, private val sessions: SessionCoordinator) {
    private val gson = Gson()
    private suspend fun call(suffix: String = "", verb: String = "GET", body: Map<String, String>? = null, request: String? = null): ManagedLease? =
        sessions.request { token ->
            val json = http.request("vpn/sessions" + suffix, verb,
                if (verb == "POST") gson.toJson(body ?: emptyMap<String, String>()).toRequestBody("application/json".toMediaType()) else null,
                token, headers = request?.let { mapOf("Idempotency-Key" to it) } ?: emptyMap())
            if (json.isJsonNull) null else gson.fromJson(json, ManagedLease::class.java).also {
                UUID.fromString(it.id); Instant.parse(it.expires_at)
                require(it.status in setOf("PROVISIONING", "READY", "REVOKING", "CLOSED"))
                require(it.heartbeat_seconds == 30)
            }
        }
    suspend fun connect(country: String, publicKey: String, request: String, method: String) =
        requireNotNull(call(verb = "POST", body = mapOf("country" to country, "public_key" to publicKey, "method" to method), request = request))
    suspend fun current() = call("/current")
    suspend fun get(id: String) = requireNotNull(call("/${UUID.fromString(id)}"))
    suspend fun heartbeat(id: String) = requireNotNull(call("/${UUID.fromString(id)}/heartbeat", "POST"))
    suspend fun revoke(id: String) = requireNotNull(call("/${UUID.fromString(id)}", "DELETE"))
}
