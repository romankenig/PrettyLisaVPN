package com.prettylisavpn.android.ui

import com.prettylisavpn.android.vpn.TrafficService
import java.text.Collator
import java.util.Locale

internal fun serviceGroups(services: List<TrafficService>, mode: String, locale: Locale, savedSelection: Set<String> = emptySet()): List<Pair<String, List<TrafficService>>> {
    val collator = Collator.getInstance(locale).apply { strength = Collator.PRIMARY }
    val all = services.distinctBy { it.id }.sortedWith { a, b -> collator.compare(a.name, b.name).takeIf { it != 0 } ?: a.id.compareTo(b.id) }
    val category = if (mode == "exclude" && locale.language == "ru") "whitelist" else "popular"
    val top = all.filter { (it.category ?: "popular") == category }.sortedBy { it.popularity_rank ?: 1001 }.take(10)
    val popular = top.map { it.id }.toSet()
    return listOf("selected" to all.filter { it.id in savedSelection },
        "top" to top.filter { it.id !in savedSelection },
        "all" to all.filter { it.id !in savedSelection && it.id !in popular })
}
