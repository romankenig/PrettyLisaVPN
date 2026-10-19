package com.prettylisavpn.android

import android.os.ParcelFileDescriptor
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.DataInputStream
import java.io.File
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class NavigationTest {
    @get:Rule
    val compose = createAndroidComposeRule<MainActivity>()

    @Test
    fun launchAndAllTabs() {
        compose.onNodeWithTag("screen_HOME").assertIsDisplayed()
        compose.onNodeWithTag("connect").assertIsNotEnabled()
        screenshot("home")
        compose.onNodeWithTag("tab_SETTINGS").performClick().assertIsSelected()
        compose.onNodeWithTag("screen_SETTINGS").assertIsDisplayed()
        screenshot("settings")
        compose.onNodeWithTag("tab_ABOUT").performClick().assertIsSelected()
        compose.onNodeWithTag("screen_ABOUT").assertIsDisplayed()
        screenshot("about")
    }

    @Test
    fun repeatedTabDoesNotAccumulateBackStack() {
        compose.onNodeWithTag("tab_SETTINGS").performClick()
        repeat(3) { compose.onNodeWithTag("tab_ABOUT").performClick() }
        compose.runOnUiThread { compose.activity.onBackPressedDispatcher.onBackPressed() }
        compose.onNodeWithTag("screen_HOME").assertIsDisplayed()
        compose.onNodeWithTag("tab_HOME").assertIsSelected()
    }

    @Test
    fun recreationRestoresSelectedTab() {
        compose.onNodeWithTag("tab_ABOUT").performClick()
        compose.activityRule.scenario.recreate()
        compose.onNodeWithTag("screen_ABOUT").assertIsDisplayed()
        compose.onNodeWithTag("tab_ABOUT").assertIsSelected()
        compose.runOnUiThread { compose.activity.onBackPressedDispatcher.onBackPressed() }
        compose.onNodeWithTag("screen_HOME").assertIsDisplayed()
    }

    private fun screenshot(name: String) {
        listOf("HOME", "SETTINGS", "ABOUT").forEach {
            compose.onNodeWithTag("tab_$it").assertIsDisplayed()
        }
        compose.waitForIdle()
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        // Compose's virtual clock becoming idle does not fence SurfaceFlinger frames.
        // Wait for native UI quietness, then capture the display through screencap.
        instrumentation.waitForIdleSync()
        instrumentation.uiAutomation.waitForIdle(250, 5_000)
        val directory = File(instrumentation.targetContext.getExternalFilesDir(null), "acceptance")
        check(directory.mkdirs() || directory.isDirectory)
        val target = File(directory, "$name.png")
        ParcelFileDescriptor.AutoCloseInputStream(
            instrumentation.uiAutomation.executeShellCommand("screencap -p"),
        ).use { input ->
            target.outputStream().use { output -> input.copyTo(output) }
        }
        val header = ByteArray(8)
        target.inputStream().use { DataInputStream(it).readFully(header) }
        check(header.contentEquals(
            byteArrayOf(0x89.toByte(), 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A),
        )) { "Native screencap did not return PNG" }
    }
}
