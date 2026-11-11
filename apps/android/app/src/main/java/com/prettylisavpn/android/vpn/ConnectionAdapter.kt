package com.prettylisavpn.android.vpn

data class VpnMethod(val id: String, val label: String) { val shortLabel get() = label }
/** Display fallback from the allocated session, never proof of tunnel health. */
data class VpnEgress(val sessionId: String, val country: String, val ip: String?)
sealed interface ConnectionResult {
    data object Failed : ConnectionResult
    /** Only return after the real adapter has verified Internet through its own tunnel. */
    data object Verified : ConnectionResult
}
interface ConnectionAdapter {
    val method: VpnMethod
    val egress: VpnEgress? get() = null
    suspend fun connect(country: String): ConnectionResult
    suspend fun disconnect()
    suspend fun recover() {}
    suspend fun health(): TunnelHealth = TunnelHealth.UNKNOWN
}

enum class TunnelHealth { HEALTHY, UNREACHABLE, NO_NETWORK, UNKNOWN, SUSPENDED }

data class ConnectionHealthPolicy(
    val intervalMillis: Long = 30_000,
    val retryMillis: Long = 5_000,
    val failureThreshold: Int = 3,
    val maxRecoveries: Int = 3,
    val recoveryWindowMillis: Long = 10 * 60_000,
    val recoveryBackoffMillis: Long = 3_000,
)
