package com.prettylisavpn.android.data

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class BillingPortalTest {
    @Test fun portalCannotRedirectToAnotherHostOrPutTokenInQuery() {
        val url = "https://prettylisavpn.com/account/#handoff=" + "a".repeat(43)
        assertTrue(validBillingPortal(url))
        for (value in listOf(url.replace(".com", ".com.evil.test"), url.replace("#", "?"), url + "&redirect=evil", "javascript:alert(1)")) {
            assertFalse(validBillingPortal(value))
        }
    }
}
