package com.prettylisavpn.android.vpn

import kotlinx.coroutines.delay

// Debug-only failure fixtures; the release and live host use real adapters.
const val PLACEHOLDER_DELAY_MILLIS = 3_000L
fun placeholder(id: String, name: String) = object : ConnectionAdapter {
    override val method = VpnMethod(id, name)
    override suspend fun connect(country: String): ConnectionResult {
        delay(PLACEHOLDER_DELAY_MILLIS)
        return ConnectionResult.Failed
    }
    override suspend fun disconnect() {}
}
