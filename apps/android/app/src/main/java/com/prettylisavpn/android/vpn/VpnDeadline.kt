package com.prettylisavpn.android.vpn

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withTimeout

internal class VpnOperationTimeout(cause: Throwable) : IllegalStateException("VPN_OPERATION_TIMEOUT", cause)

/** An adapter's deadline is a failed attempt; cancellation by its owner still cancels the loop. */
internal suspend fun <T> vpnDeadline(milliseconds: Long, operation: suspend CoroutineScope.() -> T): T =
    try { withTimeout(milliseconds, operation) }
    catch (timeout: TimeoutCancellationException) {
        currentCoroutineContext().ensureActive()
        throw VpnOperationTimeout(timeout)
    }
