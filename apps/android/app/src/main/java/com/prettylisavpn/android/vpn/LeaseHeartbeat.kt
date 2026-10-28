package com.prettylisavpn.android.vpn

import com.prettylisavpn.android.auth.AuthFailure
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.withTimeoutOrNull

/** Heartbeats reconcile server-owned access; Android sleep is not a disconnect.
 * Legacy servers still require the original 70s budget below their 90s timeout.
 * Network calls have their own HTTP timeouts; no timer enclosing a sleep/delay
 * may tear down a verified tunnel on a sleep-tolerant server.
 */
internal suspend fun maintainLeaseHeartbeat(
    intervalMillis: Long = 30_000,
    retryMillis: Long = 3_000,
    budgetMillis: Long = 70_000,
    renew: suspend () -> Boolean,
    lost: () -> Unit,
    heartbeatRequired: Boolean = true,
) {
    if (!heartbeatRequired) {
        while (true) {
            delay(intervalMillis)
            val acknowledged = try { renew() }
            catch (cancel: CancellationException) { throw cancel }
            catch (failure: AuthFailure) {
                // An ambiguous refresh remains unreplayable in SessionCoordinator.
                // It is not proof that the server revoked this existing VPN lease.
                if (failure.code in setOf("offline", "network_uncertain", "service_unavailable", "rotation_uncertain")) null else false
            } catch (_: Exception) { false }
            if (acknowledged == false) { lost(); return }
        }
    }
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
