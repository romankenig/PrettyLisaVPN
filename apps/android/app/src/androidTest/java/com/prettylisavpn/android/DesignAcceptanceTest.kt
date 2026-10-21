package com.prettylisavpn.android

import android.graphics.Bitmap
import android.content.pm.ActivityInfo
import android.os.ParcelFileDescriptor
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsFocused
import androidx.compose.ui.test.click
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertTextEquals
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.performTextReplacement
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.unit.dp
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.prettylisavpn.android.ui.Brand
import com.prettylisavpn.android.ui.BrandActionButton
import com.prettylisavpn.android.ui.BrandCard
import com.prettylisavpn.android.ui.BrandTextField
import com.prettylisavpn.android.ui.PrettyLisaTheme
import java.io.File
import java.io.DataInputStream
import org.json.JSONObject
import org.junit.Before
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class DesignAcceptanceTest {
    @get:Rule
    val compose = createAndroidComposeRule<MainActivity>()
    private var passed = false

    @Before
    fun verifyActualFontScale() {
        val arguments = InstrumentationRegistry.getArguments()
        val width = arguments.getString("widthPx")?.toInt()
        val height = arguments.getString("heightPx")?.toInt()
        if (width != null && height != null) {
            if (width > height) {
                // A fresh Activity can inherit portrait from Launcher even with user rotation locked.
                // Request the actual landscape configuration before installing test-only content.
                compose.runOnUiThread {
                    compose.activity.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE
                }
            }
            compose.waitUntil(10_000) {
                val size = windowSize()
                size.x == width && size.y == height && compose.activity.hasWindowFocus()
            }
            InstrumentationRegistry.getInstrumentation().uiAutomation.waitForIdle(1_000, 5_000)
            compose.waitForIdle()
        }
        compose.waitUntil(10_000) { compose.onAllNodesWithTag("brand-logo").fetchSemanticsNodes().isNotEmpty() }
        val expected = arguments.getString("fontScale")?.toFloat()
        if (expected != null) assertEquals(expected, compose.activity.resources.configuration.fontScale, 0.02f)
    }

    @After
    fun captureFailureBeforeActivityCloses() {
        if (!passed) runCatching { capture("failure", settle = false) }
    }

    @Test
    fun screensRespectSystemBarsTouchTargetsAndTextScale() {
        compose.onNodeWithTag("brand-logo").assertIsDisplayed()
        assertNavigationInsets()
        assertTextFits()
        capture("home")
        compose.onNodeWithTag("connect").performScrollTo().assertIsEnabled().assertIsDisplayed()
        for (tab in listOf("SETTINGS", "ABOUT")) {
            compose.onNodeWithTag("tab_$tab").performClick()
            compose.onNodeWithTag("screen_$tab").assertIsDisplayed()
            assertNavigationInsets()
            assertTextFits()
            if (tab == "ABOUT") {
                compose.onNodeWithTag("about-frontend-version").assertTextEquals(BuildConfig.VERSION_NAME)
                compose.onNodeWithTag("about-faq-title").performScrollTo().assertTextEquals("faq")
                compose.onNodeWithTag("about-dedication").performScrollTo().assertTextEquals("inspired by love of my life, Lisa")
                // Keep the main evidence frame at the version/FAQ section; content below scrolls on phones.
                compose.onNodeWithTag("about-frontend-version").performScrollTo()
            }
            capture(tab.lowercase())
        }
        passed = true
    }

    @Test
    fun supportDraftHandlesKeyboardValidationAndRecreation() {
        compose.onNodeWithTag("tab_ABOUT").performClick()
        compose.onNodeWithTag("open-support").performScrollTo().performClick()
        compose.onNodeWithTag("screen_SUPPORT").assertIsDisplayed()
        enterField("support-subject", "VPN")
        enterField("support-description", "Connection")
        enterField("support-email", "invalid")
        compose.onNodeWithText(compose.activity.getString(R.string.invalid_email)).assertExists()
        compose.waitUntil(10_000) { keyboardVisible() }
        compose.onNodeWithText(compose.activity.getString(R.string.invalid_email)).performScrollTo().assertIsDisplayed()
        compose.onNodeWithTag("support-email").assertIsDisplayed()
        assertFocusedFieldAboveKeyboard()
        assertFooterInsets()
        compose.onNodeWithTag("tab_HOME").assertDoesNotExist()
        capture("support-keyboard-error")
        compose.onNodeWithTag("support-send").performScrollTo().assertIsDisplayed().assertIsNotEnabled()
        compose.onNodeWithTag("support-email").performScrollTo().performTextReplacement("test@example.invalid")
        compose.onNodeWithText(compose.activity.getString(R.string.invalid_email)).assertDoesNotExist()
        compose.onNodeWithTag("support-subject").assertTextEquals("VPN")
        compose.onNodeWithTag("support-description").assertTextEquals("Connection")
        compose.onNodeWithTag("support-email").assertTextEquals("test@example.invalid")
        capture("support-before-recreation")
        compose.activityRule.scenario.recreate()
        compose.onNodeWithTag("support-subject").assertTextEquals("VPN")
        compose.onNodeWithTag("support-description").assertTextEquals("Connection")
        compose.onNodeWithTag("support-email").assertTextEquals("test@example.invalid")
        val activity = compose.activity
        compose.runOnUiThread {
            WindowInsetsControllerCompat(activity.window, activity.window.decorView).hide(WindowInsetsCompat.Type.ime())
        }
        compose.waitUntil(10_000) { !keyboardVisible() }
        compose.onNodeWithTag("support-send").performScrollTo().assertIsEnabled()
        capture("support-filled")
        compose.onNodeWithTag("support-back").performScrollTo().performClick()
        compose.onNodeWithTag("confirm-dialog").performClick()
        compose.onNodeWithTag("screen_ABOUT").assertIsDisplayed()
        passed = true
    }

    @Test
    fun actualComponentsExposeEnabledDisabledLoadingAndErrorStates() {
        var clicks = 0
        val activity = compose.activity
        compose.runOnUiThread {
            activity.setContent {
                PrettyLisaTheme {
                    Column(
                        Modifier.fillMaxSize().background(Brand.PurpleHeart)
                            .windowInsetsPadding(WindowInsets.safeDrawing)
                            .verticalScroll(rememberScrollState()).padding(20.dp),
                        verticalArrangement = Arrangement.spacedBy(20.dp),
                    ) {
                        Text("состояния элементов", color = Brand.Mercury, style = MaterialTheme.typography.headlineSmall)
                        BrandCard {
                            BrandActionButton("продолжить", { clicks++ }, Modifier.testTag("normal"))
                            BrandActionButton("продолжить", { clicks++ }, Modifier.testTag("loading"), loading = true)
                            BrandActionButton("недоступно", { clicks++ }, Modifier.testTag("disabled"), enabled = false)
                            BrandTextField("invalid", {}, "email", Modifier.testTag("error-field"), error = activity.getString(R.string.invalid_email))
                        }
                    }
                }
            }
        }
        compose.onNodeWithTag("normal").performClick()
        compose.runOnIdle { assertEquals(1, clicks) }
        compose.onNodeWithTag("loading").assertIsNotEnabled()
        compose.onNodeWithTag("disabled").assertIsNotEnabled()
        assertTextFits()
        capture("components")
        passed = true
    }

    private fun enterField(tag: String, value: String) {
        // Do not inject through a system dialog; require the actual foreground window and touch.
        compose.waitUntil(10_000) { compose.activity.hasWindowFocus() }
        val field = compose.onNodeWithTag(tag).performScrollTo()
        compose.waitForIdle()
        val automation = InstrumentationRegistry.getInstrumentation().uiAutomation
        // Fence the previous field's native IME animation before calculating touch coordinates.
        automation.waitForIdle(500, 5_000)
        field.performTouchInput { click() }
        compose.waitUntil(5_000) {
            field.fetchSemanticsNode().config.getOrNull(SemanticsProperties.Focused) == true
        }
        field.assertIsFocused().performTextInput(value)
        compose.waitUntil(10_000) { keyboardVisible() }
        automation.waitForIdle(500, 5_000)
        compose.waitForIdle()
    }

    private fun keyboardVisible(): Boolean =
        ViewCompat.getRootWindowInsets(compose.activity.window.decorView)?.isVisible(WindowInsetsCompat.Type.ime()) == true

    private fun assertFocusedFieldAboveKeyboard() {
        val bounds = compose.onNodeWithTag("support-email").fetchSemanticsNode().boundsInWindow
        compose.runOnIdle {
            val view = compose.activity.window.decorView
            val insets = checkNotNull(ViewCompat.getRootWindowInsets(view))
            val frame = android.graphics.Rect()
            view.getWindowVisibleDisplayFrame(frame)
            val location = IntArray(2)
            view.getLocationOnScreen(location)
            val keyboardTop = minOf(windowSize().y - insets.getInsets(WindowInsetsCompat.Type.ime()).bottom, frame.bottom)
            assertTrue("Focused field obscured by IME: $bounds", bounds.bottom + location[1] <= keyboardTop + 2)
        }
    }

    @Suppress("DEPRECATION")
    private fun windowSize(): android.graphics.Point {
        if (android.os.Build.VERSION.SDK_INT >= 30) {
            val bounds = compose.activity.windowManager.currentWindowMetrics.bounds
            return android.graphics.Point(bounds.width(), bounds.height())
        }
        return android.graphics.Point().also { compose.activity.windowManager.defaultDisplay.getRealSize(it) }
    }

    private fun assertNavigationInsets() {
        assertFooterInsets()
        val footerTop = compose.onNodeWithTag("component-versions").fetchSemanticsNode().boundsInWindow.top
        val density = compose.activity.resources.displayMetrics.density
        val bounds = listOf("HOME", "SETTINGS", "ABOUT").map {
            compose.onNodeWithTag("tab_$it").assertIsDisplayed().fetchSemanticsNode().boundsInWindow
        }
        compose.runOnIdle {
            val view = compose.activity.window.decorView
            val bars = checkNotNull(ViewCompat.getRootWindowInsets(view))
                .getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
            val size = windowSize()
            val location = IntArray(2)
            view.getLocationOnScreen(location)
            bounds.forEach {
                assertTrue("Navigation overlaps version footer: $it", it.bottom <= footerTop + 2)
                assertTrue("Touch target narrower than 48dp: $it", it.width + 1 >= 48 * density)
                assertTrue("Touch target shorter than 48dp: $it", it.height + 1 >= 48 * density)
                assertTrue("Navigation overlaps system bars: $it", it.bottom + location[1] <= size.y - bars.bottom + 2)
                assertTrue("Navigation overlaps cutout: $it", it.left + location[0] >= bars.left && it.right + location[0] <= size.x - bars.right + 2)
            }
        }
    }

    private fun assertFooterInsets() {
        compose.onNodeWithTag("app-version-footer").assertIsDisplayed()
        val text = compose.onNodeWithTag("component-versions").assertIsDisplayed().fetchSemanticsNode().boundsInWindow
        compose.runOnIdle {
            val view = compose.activity.window.decorView
            val insets = checkNotNull(ViewCompat.getRootWindowInsets(view))
            val bottom = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout() or WindowInsetsCompat.Type.ime()).bottom
            val location = IntArray(2)
            view.getLocationOnScreen(location)
            val visible = android.graphics.Rect().also { view.getWindowVisibleDisplayFrame(it) }
            assertTrue("Version text overlaps system bars or IME: $text", text.bottom + location[1] <= minOf(windowSize().y - bottom, visible.bottom) + 2)
        }
    }

    private fun assertTextFits() {
        val nodes = compose.onAllNodes(
            SemanticsMatcher.keyIsDefined(SemanticsActions.GetTextLayoutResult), useUnmergedTree = true,
        ).fetchSemanticsNodes()
        compose.runOnIdle {
            nodes.filter { !it.config.contains(SemanticsProperties.EditableText) }.forEach { node ->
                val results = mutableListOf<TextLayoutResult>()
                node.config.getOrNull(SemanticsActions.GetTextLayoutResult)?.action?.invoke(results)
                results.forEach { result ->
                    // The Text semantics adapter can retain a full-constraint paragraph while
                    // reporting an intrinsic-width node. Check actual line spans, not that container.
                    val paragraph = result.multiParagraph
                    val wideLine = (0 until result.lineCount).any { line ->
                        result.getLineRight(line) - result.getLineLeft(line) > result.size.width + 1f
                    }
                    val clipped = wideLine || paragraph.didExceedMaxLines || paragraph.height > result.size.height + 1f
                    assertFalse(
                        "Text clipped: ${result.layoutInput.text}; size=${result.size}; paragraph=${paragraph.width}x${paragraph.height}; constraints=${result.layoutInput.constraints}",
                        clipped,
                    )
                }
            }
        }
    }

    private fun capture(name: String, settle: Boolean = true) {
        if (settle) compose.waitForIdle()
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        instrumentation.waitForIdleSync()
        if (settle) instrumentation.uiAutomation.waitForIdle(250, 5_000)
        val case = InstrumentationRegistry.getArguments().getString("designCase", "compact")
        check(case.matches(Regex("[a-z0-9-]+")))
        val directory = File(instrumentation.targetContext.getExternalFilesDir(null), "acceptance/$case")
        check(directory.mkdirs() || directory.isDirectory)
        val target = File(directory, "$name.png")
        // Native display capture includes the real IME and bars, respecting logical display size
        // on old Android where shell screencap can retain the pre-wm physical composition.
        val screenshot = instrumentation.uiAutomation.takeScreenshot()
        val captureMethod = if (screenshot != null) {
            try {
                target.outputStream().use { check(screenshot.compress(Bitmap.CompressFormat.PNG, 100, it)) }
            } finally {
                screenshot.recycle()
            }
            "ui-automation"
        } else {
            // Some old Android display/rotation combinations cannot use UiAutomation capture.
            // Keep the unmodified native display PNG, and record the method explicitly.
            ParcelFileDescriptor.AutoCloseInputStream(
                instrumentation.uiAutomation.executeShellCommand("screencap -p"),
            ).use { input -> target.outputStream().use { input.copyTo(it) } }
            "shell-screencap"
        }
        val header = ByteArray(8)
        target.inputStream().use { DataInputStream(it).readFully(header) }
        val metrics = compose.activity.resources.displayMetrics
        val window = windowSize()
        val metadata = JSONObject()
            .put("capture_method", captureMethod)
            .put("source_sha", BuildConfig.SOURCE_SHA)
            .put("version_name", BuildConfig.VERSION_NAME)
            .put("version_code", BuildConfig.VERSION_CODE)
            .put("application_id", BuildConfig.APPLICATION_ID)
            .put("case", case)
            .put("font_scale", compose.activity.resources.configuration.fontScale)
            .put("density", metrics.density)
            .put("window_width_px", window.x)
            .put("window_height_px", window.y)
            .put("width_px", metrics.widthPixels)
            .put("height_px", metrics.heightPixels)
            .put("ime_visible", keyboardVisible())
        File(directory, "$name.json").writeText(metadata.toString(2))
        check(header.contentEquals(byteArrayOf(0x89.toByte(), 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A)))
    }
}
