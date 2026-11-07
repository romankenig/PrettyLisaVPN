package com.prettylisavpn.android

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.prettylisavpn.android.auth.demoDeviceKey
import java.io.File
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/** Only the disposable emulator's digest is compared by the runner, then deleted. */
@RunWith(AndroidJUnit4::class)
class DemoDeviceIdentityTest {
    @Test fun captureScopedIdentityForReinstallComparison() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val value = demoDeviceKey(context)
        assertTrue(value.matches(Regex("[a-f0-9]{64}")))
        File(context.filesDir,"demo-reinstall-key").writeText(value)
    }
}
