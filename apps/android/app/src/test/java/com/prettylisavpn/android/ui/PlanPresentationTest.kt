package com.prettylisavpn.android.ui

import org.junit.Assert.assertEquals
import org.junit.Test

class PlanPresentationTest {
    @Test fun knownPlansShareBadgesAcrossProfileAndBilling() {
        for ((name, label) in listOf("Demo" to "DEMO ⏳", "Free" to "FREE 🕊️", "Premium" to "PREMIUM ⭐", "Platinum" to "PLATINUM 💎")) {
            assertEquals(label, planLabel(name))
            assertEquals(label, planLabel(name.uppercase(java.util.Locale.ROOT)))
        }
        assertEquals("future plan", planLabel("future plan"))
    }
}
