package com.prettylisavpn.android.vpn

import kotlinx.coroutines.delay

data class VpnMethod(val id: String, val label: String) { val shortLabel get() = label }
sealed interface ConnectionResult {
    data object Failed : ConnectionResult
    /** Only return after the real adapter has verified Internet through its own tunnel. */
    data object Verified : ConnectionResult
}
interface ConnectionAdapter {
    val method: VpnMethod
    suspend fun connect(country: String): ConnectionResult
    suspend fun disconnect()
    suspend fun recover() {}
}
const val PLACEHOLDER_DELAY_MILLIS = 3_000L
fun placeholder(id: String, name: String) = object : ConnectionAdapter {
    override val method = VpnMethod(id, name)
    override suspend fun connect(country: String): ConnectionResult {
        delay(PLACEHOLDER_DELAY_MILLIS)
        return ConnectionResult.Failed
    }
    override suspend fun disconnect() {}
}
