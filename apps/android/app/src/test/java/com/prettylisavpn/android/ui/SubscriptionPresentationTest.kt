package com.prettylisavpn.android.ui

import com.prettylisavpn.android.data.*
import java.util.Locale
import org.junit.Assert.*
import org.junit.Test

class SubscriptionPresentationTest {
    @Test fun moneyKeepsCentsWithoutAddingUnnecessaryDecimals() {
        assertEquals("399 ₽", subscriptionMoney(39900, "RUB", Locale.forLanguageTag("ru")))
        assertEquals("399,50 ₽", subscriptionMoney(39950, "RUB", Locale.forLanguageTag("ru")))
        assertEquals("${'$'}5", subscriptionMoney(500, "USD", Locale.US))
        assertEquals("${'$'}5.25", subscriptionMoney(525, "USD", Locale.US))
    }
    @Test fun contractPriceIsNotReplacedByANewOffer() {
        assertEquals("RUB" to OfferPrice(19900), subscriptionContractPrice("RUB 199.00"))
        assertEquals("USD" to OfferPrice(725), subscriptionContractPrice("USD 7.25"))
        for (value in listOf(null, "unavailable", "RUB -1.00", "RUB 1.001", "RUB 999999999999999999999", "EUR 5.00")) {
            assertNull(subscriptionContractPrice(value))
        }
    }
    @Test fun routeChoicesOnlyContainUsablePurchaseCapabilities() {
        val routes = routeIds.map { PaymentRoute(it, it, if (it == "MIR") setOf("RUB") else emptySet(), emptySet()) }
        val billing = BillingOverview("r1", "LIVE", true, "FREE", "NONE", null, false, null, null,
            routes, emptyList(), setOf("SUBSCRIBE"), null)
        assertEquals(listOf("MIR"), subscriptionPurchaseRoutes(billing, "RUB").map { it.id })
        assertTrue(subscriptionPurchaseRoutes(billing, "USD").isEmpty())
        assertTrue(subscriptionPurchaseRoutes(billing.copy(mode = "DISABLED"), "RUB").isEmpty())
        assertTrue(subscriptionPurchaseRoutes(billing.copy(mode = "SANDBOX"), "RUB").isEmpty())
        assertTrue(subscriptionPurchaseRoutes(billing.copy(available = false), "RUB").isEmpty())
        assertTrue(subscriptionPurchaseRoutes(billing.copy(actions = setOf("CANCEL")), "RUB").isEmpty())
        assertTrue(subscriptionPurchaseRoutes(billing.copy(pendingId = "pending"), "RUB").isEmpty())
    }
}
