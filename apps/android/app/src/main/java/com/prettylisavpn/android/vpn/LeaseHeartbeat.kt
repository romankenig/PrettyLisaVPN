package com.prettylisavpn.android.vpn

import com.prettylisavpn.android.auth.AuthFailure
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.withTimeoutOrNull

/** Retry only safe lease renewal. Never replay arbitrary authenticated mutations.
 * The 70s budget includes the normal interval and stays below the server's 90s
 * deadline, allowing for at most one bounded 15s blocking HTTP call to unwind.
 */
internal suspend fun maintainLeaseHeartbeat(
    intervalMillis: Long = 30_000,
    retryMillis: Long = 3_000,
    budgetMillis: Long = 70_000,
    renew: suspend () -> Boolean,
    lost: () -> Unit,
) {
    while (true) {
        val acknowledged = withTimeoutOrNull(budgetMillis) {
            delay(intervalMillis)
            while (true) {
                try { return@withTimeoutOrNull renew() }
                catch (cancel: CancellationException) { throw cancel }
                catch (failure: AuthFailure) {
                    if (failure.code !in setOf("offline", "network_uncertain", "service_unavailable")) return@withTimeoutOrNull false
                } catch (_: Exception) { return@withTimeoutOrNull false }
                delay(retryMillis)
            }
            @Suppress("UNREACHABLE_CODE") false
        }
        if (acknowledged != true) { lost(); return }
    }
}
