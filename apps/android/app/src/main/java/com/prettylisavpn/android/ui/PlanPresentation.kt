package com.prettylisavpn.android.ui

internal fun planLabel(plan: String): String = when {
    plan.equals("Demo", ignoreCase = true) -> "DEMO 🌱"
    plan.equals("Free", ignoreCase = true) -> "Free 🆓"
    plan.equals("Premium", ignoreCase = true) -> "Premium ⭐"
    plan.equals("Platinum", ignoreCase = true) -> "Platinum 💎"
    else -> plan
}
