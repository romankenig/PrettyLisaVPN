package com.prettylisavpn.android.vpn

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
