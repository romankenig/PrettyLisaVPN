package com.prettylisavpn.android.data

import com.prettylisavpn.android.auth.AuthFailure
import kotlinx.coroutines.delay

/** Only read operations may retry; uncertain mutations must retain their journal. */
internal suspend fun <T> readWithNetworkGrace(
    graceMillis: Long = 15_000,
    now: () -> Long = { System.nanoTime() / 1_000_000 },
    pause: suspend (Long) -> Unit = { delay(it) },
    read: suspend () -> T,
): T {
    var failedAt: Long? = null
    while (true) {
        try { return read() } catch (error: AuthFailure) {
            if (error.code !in setOf("offline", "network_uncertain")) throw error
            val start = failedAt ?: now().also { failedAt = it }
            val remaining = graceMillis - (now() - start)
            if (remaining <= 0) throw error
            pause(minOf(3_000, remaining))
        }
    }
}
