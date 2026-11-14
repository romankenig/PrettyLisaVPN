package com.prettylisavpn.android.ui

import com.prettylisavpn.android.vpn.VpnEgress

internal data class LocationDisplay(val value: PublicLocation?, val expected: Boolean = false)

/** Observations win; fallback sources must match the selected traffic path. */
internal fun secondaryLocation(
    mode: String,
    observed: PublicLocation?,
    egress: VpnEgress?,
    direct: PublicLocation?,
): LocationDisplay {
    val fallback = when (mode) {
        "include" -> egress?.let { PublicLocation(it.ip, it.country.takeIf { code -> code.matches(Regex("[A-Z]{2}")) }, null) }
        "exclude" -> direct
        else -> null
    }
    if (observed == null) return LocationDisplay(fallback, expected = fallback != null)
    // Do not combine a measured address with a city belonging to another IP.
    val country = observed.country ?: fallback?.country
    val city = observed.city ?: fallback?.city?.takeIf { fallback.ip == observed.ip }
    return LocationDisplay(observed.copy(country = country, city = city),
        expected = country != observed.country || city != observed.city)
}
