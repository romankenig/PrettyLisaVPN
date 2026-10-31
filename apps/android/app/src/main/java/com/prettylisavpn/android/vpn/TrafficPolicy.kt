package com.prettylisavpn.android.vpn

import com.google.gson.Gson
import java.net.IDN
import java.util.Locale
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.withTimeout

data class TrafficService(val id: String, val slug: String, val name: String, val icon: String, val domains: List<String>, val category: String? = null)
data class TrafficList(val services: List<TrafficService> = emptyList(), val masks: List<String> = emptyList())
data class TrafficSelection(val mode: String = "all", val include: TrafficList = TrafficList(), val exclude: TrafficList = TrafficList())
data class RoutingPolicy(val mode: String, val domains: List<String>)

fun TrafficSelection.refreshServices(catalog: List<TrafficService>): TrafficSelection {
    fun refresh(list: TrafficList) = list.copy(services = list.services.map { saved -> catalog.find { it.id == saved.id } ?: saved })
    return copy(include = refresh(include), exclude = refresh(exclude))
}

fun normalizeTrafficMask(input: String): String {
    val raw = input.trim().lowercase(Locale.ROOT)
    val wildcard = raw.startsWith("*.")
    val value = raw.removePrefix("*.")
    require(value.isNotEmpty() && !value.any { it.isWhitespace() || it in "/:@?#\\*%" })
    val host = IDN.toASCII(value, IDN.USE_STD3_ASCII_RULES).lowercase(Locale.ROOT)
    val parts = host.split('.')
    require(host.length <= 253 && parts.size >= 2 && parts.last().any { it in 'a'..'z' })
    require(parts.all { it.matches(Regex("[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")) })
    return (if (wildcard) "*." else "") + host
}
fun validateTrafficServices(values: List<TrafficService>): List<TrafficService> {
    require(values.size <= 64 && values.map { it.id }.distinct().size == values.size)
    return values.map { value ->
        require(value.id.matches(Regex("[0-9a-f-]{36}")) && value.slug.matches(Regex("[a-z][a-z0-9-]{0,39}")) && value.icon.matches(Regex("[a-z][a-z0-9-]{0,39}")))
        require(value.category == null || value.category in setOf("popular", "whitelist"))
        require(value.name.length in 1..80 && value.domains.size in 1..64)
        value.copy(domains = value.domains.map(::normalizeTrafficMask).distinct())
    }
}
fun TrafficSelection.policy(): RoutingPolicy {
    require(mode in setOf("all", "include", "exclude"))
    if (mode == "all") return RoutingPolicy(mode, emptyList())
    val list = if (mode == "include") include else exclude
    val domains = (list.masks.map(::normalizeTrafficMask) + validateTrafficServices(list.services).flatMap { it.domains }).distinct()
    require(domains.size <= 256)
    return RoutingPolicy(mode, domains)
}
class TrafficPreference(read: () -> String? = { null }, private val write: (String) -> Unit = {}) {
    private val gson = Gson()
    private fun checked(value: TrafficSelection): TrafficSelection {
        value.policy(); value.copy(mode = "include").policy(); value.copy(mode = "exclude").policy()
        return value
    }
    private val mutable = MutableStateFlow(runCatching { read()?.let { checked(gson.fromJson(it, TrafficSelection::class.java)) } }.getOrNull() ?: TrafficSelection())
    val selected = mutable.asStateFlow()
    fun current() = mutable.value
    fun save(value: TrafficSelection) { checked(value); write(gson.toJson(value)); mutable.value = value }
}

/** Saving never reconnects and cannot commit rules before confirmed cleanup. */
suspend fun applyTrafficSelection(next: TrafficSelection, store: TrafficPreference, vpn: VpnActions?) {
    next.policy(); next.copy(mode = "include").policy(); next.copy(mode = "exclude").policy()
    if (vpn != null && vpn.status.value.phase != VpnPhase.DISCONNECTED) {
        vpn.disconnect()
        val stopped = withTimeout(45_000) { vpn.status.first { it.phase == VpnPhase.DISCONNECTED || it.phase == VpnPhase.FAILED } }
        check(stopped.phase == VpnPhase.DISCONNECTED)
    }
    store.save(next)
}
