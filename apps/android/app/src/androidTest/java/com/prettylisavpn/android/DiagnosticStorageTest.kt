package com.prettylisavpn.android

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.prettylisavpn.android.diagnostics.*
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.time.Instant

@RunWith(AndroidJUnit4::class)
class DiagnosticStorageTest {
    @Test fun accountChangesFenceQueuedHistoryAndLogoutClearsIt() {
        val log = AppDiagnostics.get(InstrumentationRegistry.getInstrumentation().targetContext)
        log.account("synthetic-account-A")
        repeat(1000) { log.append(DiagnosticEvent(Instant.now().toString(), it.toLong(), DiagnosticKind.VPN_CONNECT, country = "DE")) }
        log.account("synthetic-account-B")
        log.append(DiagnosticEvent(Instant.now().toString(), 1001, DiagnosticKind.VPN_CONNECT, country = "US"))
        val snapshot = log.snapshot()
        assertTrue(snapshot.available)
        assertFalse(snapshot.events.any { it.country == "DE" })
        assertTrue(snapshot.events.any { it.country == "US" })
        log.account(null)
        assertFalse(log.snapshot().events.any { it.event == DiagnosticKind.VPN_CONNECT })
    }

    @Test fun actualDeviceProjectionHasNoAccountOrNetworkIdentifiers() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val projection = com.prettylisavpn.android.data.androidDiagnostics(context, null, "en", "FREE")
        assertEquals("ANDROID", projection["platform"].asString)
        assertTrue(projection["backend_version"].isJsonNull)
        assertEquals(BuildConfig.VERSION_NAME, projection["frontend_version"].asString)
        assertEquals(BuildConfig.SOURCE_SHA, projection.getAsJsonObject("device")["app_source_sha"].asString)
        for (key in listOf("email", "ip", "ssid", "android_id", "private_key", "access_token")) {
            assertFalse(projection.has(key))
            assertFalse(projection.getAsJsonObject("device").has(key))
            assertFalse(projection.getAsJsonObject("network").has(key))
        }
        val directory = java.io.File(context.getExternalFilesDir(null), "acceptance/support-diagnostics")
        check(directory.mkdirs() || directory.isDirectory)
        java.io.File(directory, "android-projection.json").writeText(projection.toString())
    }
}
