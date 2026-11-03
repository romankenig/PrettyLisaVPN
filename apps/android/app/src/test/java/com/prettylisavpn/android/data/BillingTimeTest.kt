package com.prettylisavpn.android.data

import java.time.Instant
import org.junit.Assert.*
import org.junit.Test

class BillingTimeTest {
    @Test fun remainingDaysRespectTheExclusiveDeadline() {
        val deadline = "2026-11-30T00:00:00Z"
        val end = Instant.parse(deadline)
        assertEquals(2L, remainingPaidDays(deadline, end.minusMillis(86_400_001)))
        assertEquals(1L, remainingPaidDays(deadline, end.minusMillis(1)))
        assertEquals(0L, remainingPaidDays(deadline, end))
        assertEquals(0L, remainingPaidDays(deadline, end.plusMillis(1)))
        assertNull(remainingPaidDays(null))
        assertNull(remainingPaidDays("invalid"))
    }
}
