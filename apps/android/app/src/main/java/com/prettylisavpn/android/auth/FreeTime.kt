package com.prettylisavpn.android.auth

import com.google.gson.JsonObject
import java.time.Instant

/** Read-only account balance. The backend remains authoritative for admission/expiry. */
data class FreeTime(val seconds: Int, val running: Int, val resetsAt: String, val receivedAtMillis: Long) {
    fun remaining(nowMillis: Long): Int = (seconds - ((nowMillis - receivedAtMillis).coerceAtLeast(0) / 1000).coerceAtMost(60) * running).coerceIn(0, 3600).toInt()
}

internal fun readFreeTime(json: JsonObject, nowMillis: Long = System.currentTimeMillis()): FreeTime? = runCatching {
    val rights = json.getAsJsonObject("entitlements") ?: return@runCatching null
    val seconds = (rights.get("free_seconds_usable")?.takeUnless { it.isJsonNull }
        ?: rights.get("free_seconds_remaining")?.takeUnless { it.isJsonNull })?.asInt ?: return@runCatching null
    val running = rights.get("free_running_sessions")?.takeUnless { it.isJsonNull }?.asInt ?: 0
    val resets = rights.get("free_quota_resets_at").asString
    Instant.parse(resets)
    require(seconds in 0..3600 && running in 0..5)
    FreeTime(seconds, running, resets, nowMillis)
}.getOrNull()
