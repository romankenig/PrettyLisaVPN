package com.prettylisavpn.android.ui

import com.prettylisavpn.android.vpn.TrafficService
import java.text.Collator
import java.util.Locale

internal fun serviceGroups(services: List<TrafficService>, mode: String, locale: Locale, savedSelection: Set<String> = emptySet()): List<Pair<String, List<TrafficService>>> {
    val collator = Collator.getInstance(locale)
    val all = services.sortedWith { a, b -> collator.compare(a.name, b.name).takeIf { it != 0 } ?: a.id.compareTo(b.id) }
    val category = if (mode == "exclude" && locale.language == "ru") "whitelist" else "popular"
    val order = Comparator<TrafficService> { a, b ->
        (if (b.id in savedSelection) 1 else 0).compareTo(if (a.id in savedSelection) 1 else 0)
            .takeIf { it != 0 } ?: collator.compare(a.name, b.name).takeIf { it != 0 } ?: a.id.compareTo(b.id)
    }
    val top = all.filter { (it.category ?: "popular") == category }.sortedBy { it.popularity_rank ?: 1001 }.take(10)
    return listOf("top" to top.sortedWith(order), "all" to all.sortedWith(order))
}
