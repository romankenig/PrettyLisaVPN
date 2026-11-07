package com.prettylisavpn.android.ui

internal fun planLabel(plan: String): String = when {
    plan.equals("Demo", ignoreCase = true) -> "DEMO ⏳"
    plan.equals("Free", ignoreCase = true) -> "FREE 🕊️"
    plan.equals("Premium", ignoreCase = true) -> "PREMIUM ⭐"
    plan.equals("Platinum", ignoreCase = true) -> "PLATINUM 💎"
    else -> plan
}
