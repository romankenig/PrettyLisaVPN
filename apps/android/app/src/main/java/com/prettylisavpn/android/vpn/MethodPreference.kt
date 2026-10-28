package com.prettylisavpn.android.vpn

/** Optional device-local method ID. Never persist keys, account data or endpoints. */
class MethodPreference(read: () -> String? = { null }, private val write: (String) -> Unit = {}) {
    private var method = runCatching { read()?.takeIf { it.matches(Regex("[a-z][a-z0-9_]{0,63}")) } }.getOrNull()
    fun current(): String? = method
    fun remember(verifiedMethod: String) {
        method = verifiedMethod
        // Preference storage must not turn a working VPN into a failed connection.
        runCatching { write(verifiedMethod) }
    }
}
