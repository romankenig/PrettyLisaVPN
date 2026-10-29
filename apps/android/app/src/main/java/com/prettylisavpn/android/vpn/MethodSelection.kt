package com.prettylisavpn.android.vpn

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow

val connectionMethods: List<VpnMethod> = listOf(
    "wireguard" to "WireGuard", "amneziawg" to "Amnezia", "sstp" to "SSTP",
    "softether" to "SoftEther",
    "shadowsocks2022" to "SS2022",
    "vmess" to "VMess", "vless" to "VLESS", "vless_reality" to "REALITY",
    "hysteria" to "Hysteria",
    "hysteria2" to "Hysteria 2", "hysteria2_salamander" to "Salamander",
).flatMap { (id, name) -> listOf(VpnMethod(id, name), VpnMethod("${id}_relay", "$name+")) }

/** null selects all methods, including methods added by a later app update. */
class MethodSelection(read: () -> Set<String>? = { null }, private val write: (Set<String>?) -> Unit = {}) {
    private val ids = connectionMethods.map { it.id }.toSet()
    private val mutable = MutableStateFlow(runCatching { read()?.intersect(ids)?.takeIf { it.isNotEmpty() } }.getOrNull())
    val selected = mutable.asStateFlow()
    fun current(): Set<String>? = mutable.value
    private fun save(value: Set<String>?) {
        mutable.value = value
        runCatching { write(value) }
    }
    fun all() = save(null)
    fun toggle(id: String) {
        if (id !in ids) return
        val active = mutable.value ?: ids
        val next = if (id in active) active - id else active + id
        if (next.isNotEmpty()) save(next.takeUnless { it == ids })
    }
}
