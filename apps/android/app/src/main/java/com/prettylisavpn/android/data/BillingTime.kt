package com.prettylisavpn.android.data

import java.time.Instant
import kotlin.math.ceil

/** Display only; access and renewals are always decided by the server. */
fun remainingPaidDays(until: String?, now: Instant = Instant.now()): Long? = until?.let {
    runCatching { ceil((Instant.parse(it).toEpochMilli() - now.toEpochMilli()) / 86_400_000.0).toLong().coerceAtLeast(0) }.getOrNull()
}
