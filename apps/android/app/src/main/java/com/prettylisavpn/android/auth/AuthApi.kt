package com.prettylisavpn.android.auth

import com.google.gson.Gson
import com.google.gson.JsonObject
import com.google.gson.JsonElement
import okhttp3.RequestBody
import java.io.IOException
import java.net.ConnectException
import java.net.UnknownHostException
import java.time.Instant
import java.util.UUID
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit

/** Deliberately no server body, URL, credential or IOException message in user-facing errors. */
class AuthFailure(val code: String) : Exception(when (code) {
    "BILLING_REVISION_CHANGED" -> "The price changed. Refresh and review the subscription before confirming again."
    "BILLING_ACTION_UNAVAILABLE", "BILLING_ROUTE_UNAVAILABLE", "BILLING_OFFER_UNAVAILABLE", "BILLING_CURRENCY_LOCKED", "BILLING_DISABLED" -> "This payment action is unavailable. Refresh subscription details."
    "BILLING_IDEMPOTENCY_CONFLICT", "IDEMPOTENCY_CONFLICT" -> "The saved request conflicts with the server record. Check its status before continuing."
    "BILLING_OPERATION_IN_PROGRESS" -> "Another billing operation is still pending. Refresh its status."
    "RATE_LIMITED" -> "Too many support requests. Please wait before trying again."
    "ATTACHMENT_REJECTED" -> "The selected image was rejected. Choose PNG, JPEG or WebP within the size limits."
    "INVALID_REQUEST" -> "Review the subject, description and reply address."
    "MESSAGE_NOT_FOUND" -> "This message changed or is no longer available. Refresh messages."
    "device_not_found" -> "This device is no longer available. Refresh the device list."
    "offline" -> "No network connection. Check your connection and retry."
    "otp_invalid_or_expired" -> "The code is invalid or expired. Request a new code."
    "otp_rate_limited" -> "Too many requests. Please wait before requesting another code."
    "device_limit_reached" -> "The account already has five active devices."
    "device_revoked" -> "This device has been revoked. Sign in again."
    "user_blocked" -> "Account access is blocked."
    "reauth_required", "invalid_refresh_token", "invalid_session" -> "Your session has ended. Sign in again."
    "storage_unavailable" -> "Secure storage is unavailable. Please retry."
    "rotation_uncertain" -> "Session renewal could not be confirmed. Sign in again to continue safely."
    else -> "The service is temporarily unavailable. Please retry."
})
data class Credentials(val sessionId: String, val refreshToken: String, val expiresAt: String, val rotationPending: Boolean = false) {
    override fun toString() = "Credentials([redacted])"
}
data class Tokens(val access: String, val ttlSeconds: Long, val credentials: Credentials) {
    override fun toString() = "Tokens([redacted])"
}
data class Profile(val email: String, val plan: String, val activeDevices: Int, val id: String = "")
interface AuthApi {
    suspend fun requestOtp(email: String)
    suspend fun verifyOtp(email: String, code: String, installationId: String, deviceName: String): Tokens
    suspend fun refresh(credentials: Credentials): Tokens
    suspend fun me(access: String): Profile
    suspend fun logout(access: String)
}

class HttpAuthApi(baseUrl: String, allowLoopbackForTests: Boolean = false) : AuthApi {
    private val base = baseUrl.toHttpUrl().also {
        require(it.username.isEmpty() && it.password.isEmpty() && it.query == null && it.fragment == null)
        require(it.isHttps || (allowLoopbackForTests && it.host in setOf("localhost", "127.0.0.1", "::1")))
    }
    private val client = OkHttpClient.Builder().followRedirects(false).followSslRedirects(false)
        .retryOnConnectionFailure(false).connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS).callTimeout(15, TimeUnit.SECONDS).build()
    private val gson = Gson()
    private suspend fun call(path: String, body: Map<String, String>? = null, access: String? = null): JsonObject =
        request(path, if (body == null) "GET" else "POST", body?.let { gson.toJson(it).toRequestBody("application/json".toMediaType()) }, access).asJsonObject
    internal suspend fun request(path: String, method: String = "GET", body: RequestBody? = null, access: String? = null, query: Map<String,String> = emptyMap()): JsonElement = withContext(Dispatchers.IO) {
        val url = base.newBuilder().addPathSegments(path).apply { query.forEach { (k,v) -> addQueryParameter(k,v) } }.build()
        val request = Request.Builder().url(url).method(method, body).apply {
            header("Accept", "application/json"); header("Cache-Control", "no-store")
            if (access != null) header("Authorization", "Bearer $access")
        }.build()
        try {
            val requestClient = if (path.startsWith("support/")) client.newBuilder().readTimeout(30, TimeUnit.SECONDS).callTimeout(30, TimeUnit.SECONDS).build() else client
            requestClient.newCall(request).execute().use { response ->
                val responseBody = response.body ?: throw AuthFailure("invalid_response")
                val bytes = responseBody.source().apply { request(65_537) }.buffer
                if (bytes.size > 65_536) throw AuthFailure("invalid_response")
                val json = runCatching { gson.fromJson(bytes.readUtf8(), JsonElement::class.java) }.getOrNull()
                if (!response.isSuccessful) {
                    val code = runCatching { json?.asJsonObject?.getAsJsonObject("error")?.get("code")?.asString }.getOrNull()
                    throw AuthFailure(when {
                        path !in setOf("auth/request-otp", "auth/verify-otp", "auth/refresh", "auth/logout", "me") && response.code == 401 -> "invalid_access_token"
                        code == "AUTH_INVALID" || code == "account_unavailable" -> "invalid_session"
                        code in setOf("SUPPORT_NOT_FOUND", "IDEMPOTENCY_CONFLICT", "RATE_LIMITED", "ATTACHMENT_REJECTED", "INVALID_REQUEST", "MESSAGE_NOT_FOUND", "BILLING_DISABLED", "BILLING_REVISION_CHANGED", "BILLING_ACTION_UNAVAILABLE", "BILLING_ROUTE_UNAVAILABLE", "BILLING_OFFER_UNAVAILABLE", "BILLING_CURRENCY_LOCKED", "BILLING_IDEMPOTENCY_CONFLICT", "BILLING_OPERATION_IN_PROGRESS", "BILLING_OPERATION_NOT_FOUND", "device_not_found") -> code!!
                        code in setOf("otp_invalid_or_expired", "otp_rate_limited", "device_limit_reached", "device_revoked", "user_blocked", "invalid_refresh_token", "invalid_access_token", "invalid_session", "authentication_required") -> code!!
                        response.code == 503 -> "service_unavailable"
                        else -> "http_error"
                    })
                }
                json ?: throw AuthFailure("invalid_response")
            }
        } catch (_: UnknownHostException) { throw AuthFailure("offline")
        } catch (_: ConnectException) { throw AuthFailure("offline")
        } catch (_: IOException) { throw AuthFailure("network_uncertain") }
    }
    private fun JsonObject.text(key: String): String = runCatching { get(key).asString }.getOrNull()?.takeIf { it.isNotBlank() } ?: throw AuthFailure("invalid_response")
    private fun tokens(json: JsonObject): Tokens = try {
        require(json.text("token_type") == "bearer")
        val session = json.text("session_id"); UUID.fromString(session)
        val expiry = json.text("refresh_token_expires_at"); Instant.parse(expiry)
        val ttl = json.get("access_token_expires_in").asLong; require(ttl > 0)
        val refresh = json.text("refresh_token"); require(refresh.length <= 512)
        Tokens(json.text("access_token"), ttl, Credentials(session, refresh, expiry))
    } catch (_: Exception) { throw AuthFailure("invalid_response") }
    override suspend fun requestOtp(email: String) {
        if (call("auth/request-otp", mapOf("email" to email)).text("status") != "accepted") throw AuthFailure("invalid_response")
    }
    override suspend fun verifyOtp(email: String, code: String, installationId: String, deviceName: String) = tokens(call("auth/verify-otp", mapOf("email" to email, "code" to code, "installation_id" to installationId, "platform" to "ANDROID", "device_name" to deviceName)))
    override suspend fun refresh(credentials: Credentials) = tokens(call("auth/refresh", mapOf("session_id" to credentials.sessionId, "refresh_token" to credentials.refreshToken)))
    override suspend fun me(access: String): Profile {
        val json = call("me", access = access)
        return try {
            val count = json.get("active_device_count").asInt; require(count in 0..5)
            val plan = json.text("plan"); require(plan in setOf("FREE", "PREMIUM", "PLATINUM"))
            Profile(json.text("email"), plan.lowercase().replaceFirstChar { it.uppercase() }, count, json.text("id").also { UUID.fromString(it) })
        } catch (_: Exception) { throw AuthFailure("invalid_response") }
    }
    override suspend fun logout(access: String) {
        if (call("auth/logout", emptyMap(), access).text("status") != "logged_out") throw AuthFailure("invalid_response")
    }
}
