package com.prettylisavpn.android

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.prettylisavpn.android.auth.Credentials
import com.prettylisavpn.android.auth.KeystoreVault
import org.junit.Test
import org.junit.Assert.*
import org.junit.runner.RunWith

/** Invoked in separate instrumentation processes, with an explicit force-stop between them. */
@RunWith(AndroidJUnit4::class)
class KeystoreRestartSeed {
    @Test fun persistPendingRotation() {
        val vault = KeystoreVault(InstrumentationRegistry.getInstrumentation().targetContext)
        vault.write(Credentials("c21132ac-0d2e-4da7-96ac-8a6ceeb019ba", "restart-test-only", "2030-01-01T00:00:00Z", true))
    }
}
@RunWith(AndroidJUnit4::class)
class KeystoreRestartCheck {
    @Test fun readAfterForceStop() {
        val vault = KeystoreVault(InstrumentationRegistry.getInstrumentation().targetContext)
        try {
            val credentials = checkNotNull(vault.read())
            assertTrue(credentials.rotationPending)
            assertEquals("restart-test-only", credentials.refreshToken)
        } finally { vault.clear() }
        assertNull(vault.read())
    }
}
