package com.prettylisavpn.android.vpn

import java.io.IOException
import kotlinx.coroutines.delay

/** Keep the same tunnel during one transient DNS/HTTPS failure at route startup. */
internal suspend fun verifyConnection(
    isUp: suspend () -> Boolean,
    pause: suspend () -> Unit = { delay(1_000) },
    probe: suspend () -> Boolean,
): Boolean {
    try { return probe() }
    catch (error: IOException) {
        if (!isUp()) throw error
        pause()
        if (!isUp()) throw error
        return probe()
    }
}
