package com.prettylisavpn.android

import android.graphics.Bitmap
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
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
        compose.waitForIdle()
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val directory = File(instrumentation.targetContext.getExternalFilesDir(null), "acceptance")
        check(directory.mkdirs() || directory.isDirectory)
        val bitmap = checkNotNull(instrumentation.uiAutomation.takeScreenshot())
        File(directory, "$name.png").outputStream().use {
            check(bitmap.compress(Bitmap.CompressFormat.PNG, 100, it))
        }
        bitmap.recycle()
    }
}
