package com.prettylisavpn.android

import android.os.ParcelFileDescriptor
import java.io.DataInputStream
import androidx.core.content.edit
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import android.os.SystemClock
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.prettylisavpn.android.auth.*
import com.prettylisavpn.android.data.*
import com.prettylisavpn.android.ui.*
import org.junit.*
import org.junit.Assert.*
import org.junit.runner.RunWith
import java.io.File
import java.util.Locale

@RunWith(AndroidJUnit4::class)
class PresentationUiTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()
    private val api = object : AuthApi {
        var requests = 0
        override suspend fun requestOtp(email: String) { requests++ }
        override suspend fun verifyOtp(email: String, code: String, installationId: String, deviceName: String): Tokens = error("No login needed")
        override suspend fun refresh(credentials: Credentials): Tokens = error("No stored credentials")
        override suspend fun me(access: String): Profile = error("No account needed")
        override suspend fun logout(access: String) = Unit
    }
    private val vault = object : CredentialVault {
        override fun read(): Credentials? = null
        override fun write(credentials: Credentials) = Unit
        override fun clear() = Unit
        override fun installationId() = "00000000-0000-0000-0000-000000000001"
    }
    private lateinit var model: ScreenModel
    private fun waitFor(tag: String) = compose.waitUntil(10_000) { compose.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty() }
    @Before fun launch() {
        SourceFactory.sourceForTests = LiveSessionSource(SessionCoordinator(api, vault, "Test Android"))
        compose.runOnUiThread {
            compose.activity.getSharedPreferences("presentation", 0).edit(commit = true) { clear() }
            PresentationStore.reset()
            compose.activity.viewModelStore.clear()
        }
        compose.activityRule.scenario.recreate()
        compose.runOnUiThread { model = compose.activity.screenModel }
        waitFor("screen_LOGIN")
    }
    @After fun reset() {
        compose.runOnUiThread {
            compose.activity.getSharedPreferences("presentation", 0).edit(commit = true) { clear() }
            PresentationStore.reset()
        }
        SourceFactory.sourceForTests = null
    }
    private fun choose(code: String) {
        compose.onNodeWithTag("language-picker").performClick()
        compose.onNodeWithTag("language-$code").performScrollTo().performClick()
        compose.waitForIdle()
    }
    private fun hideKeyboard() {
        androidx.test.espresso.Espresso.closeSoftKeyboard()
        compose.waitUntil(10_000) {
            ViewCompat.getRootWindowInsets(compose.activity.window.decorView)?.isVisible(WindowInsetsCompat.Type.ime()) != true
        }
    }
    private fun screenshot(name: String) {
        compose.runOnUiThread { compose.activity.window.decorView.invalidate() }
        compose.waitForIdle()
        val i = InstrumentationRegistry.getInstrumentation()
        i.uiAutomation.waitForIdle(500, 5_000)
        val dir = File(i.targetContext.getExternalFilesDir(null), "acceptance/ui-polish")
        check(dir.mkdirs() || dir.isDirectory)
        val target = File(dir, "$name.png")
        ParcelFileDescriptor.AutoCloseInputStream(i.uiAutomation.executeShellCommand("screencap -p")).use { input ->
            target.outputStream().use { output -> input.copyTo(output) }
        }
        val header = ByteArray(8)
        target.inputStream().use { DataInputStream(it).readFully(header) }
        check(header.contentEquals(byteArrayOf(0x89.toByte(), 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A)))
    }
    @Test fun allSixLanguagesTranslateLoginAndPreserveBrandAndDraft() {
        compose.onNodeWithTag("login-email").performTextInput("Acceptance.Case@example.com")
        androidx.test.espresso.Espresso.closeSoftKeyboard()
        for (language in AppLanguage.entries) {
            choose(language.code)
            hideKeyboard()
            compose.onNodeWithTag("header-logo").assertTextEquals("PrettyLisaVPN")
            compose.onNodeWithTag("login-email").assertTextEquals("Acceptance.Case@example.com")
            val localized = compose.activity.createConfigurationContext(android.content.res.Configuration(compose.activity.resources.configuration).apply { setLocale(Locale.forLanguageTag(language.code)) })
            compose.onNodeWithText(localized.getString(R.string.ui_sign_in_by_email)).assertExists()
            compose.onNodeWithText(localized.getString(R.string.ui_email)).assertExists()
            val english = compose.onNodeWithTag("language-english-${language.code}", useUnmergedTree = true).getUnclippedBoundsInRoot()
            val native = compose.onNodeWithTag("language-native-${language.code}", useUnmergedTree = true).getUnclippedBoundsInRoot()
            assertEquals((english.left.value + english.right.value) / 2, (native.left.value + native.right.value) / 2, 1f)
            assertTrue(english.bottom <= native.top)
            compose.onNodeWithTag("header-mark").assertWidthIsAtLeast(androidx.compose.ui.unit.Dp(44f))
            compose.onNodeWithTag("component-versions").assertTextContains(BuildConfig.VERSION_NAME, substring = true)
            compose.onNodeWithTag("live-banner").assertDoesNotExist()
            screenshot("login-${language.code}")
        }
        compose.onNodeWithTag("language-picker").performClick()
        val nodes = AppLanguage.entries.map { compose.onNodeWithTag("language-${it.code}").getUnclippedBoundsInRoot().top.value }
        assertEquals(nodes.sorted(), nodes)
        screenshot("language-menu")
    }
    @Test fun otpLinksKeepThirtySecondCooldownAndCodeDuringLanguageChanges() {
        compose.onNodeWithTag("login-email").performTextInput("Acceptance.Case@example.com")
        androidx.test.espresso.Espresso.closeSoftKeyboard()
        compose.onNodeWithTag("auth-submit").performScrollTo().performClick(); waitFor("screen_OTP")
        val deadline = model.resendAtMillis
        compose.onNodeWithTag("otp-resend").performScrollTo().assertIsNotEnabled()
        compose.onNodeWithTag("otp").performScrollTo().performTextInput("123456")
        androidx.test.espresso.Espresso.closeSoftKeyboard()
        choose("ru")
        hideKeyboard()
        assertEquals(deadline, model.resendAtMillis)
        compose.onNodeWithTag("otp").assertTextEquals("123456")
        compose.onNodeWithTag("otp-resend").performScrollTo().assertIsNotEnabled()
        val resend = compose.onNodeWithTag("otp-resend").getUnclippedBoundsInRoot().top.value
        val change = compose.onNodeWithTag("change-email").getUnclippedBoundsInRoot().top.value
        val submit = compose.onNodeWithTag("auth-submit").getUnclippedBoundsInRoot().top.value
        assertTrue(resend < submit && change < submit)
        compose.onNodeWithTag("auth-submit").performScrollTo().assertIsDisplayed()
        screenshot("otp-ru")
        compose.waitUntil(35_000) { SystemClock.elapsedRealtime() >= deadline + 300 }
        compose.onNodeWithTag("otp-resend").assertIsEnabled().performClick()
        compose.waitUntil(5_000) { api.requests == 2 && !model.state.value.busy }
        assertTrue(model.resendAtMillis > deadline)
        compose.onNodeWithTag("otp-resend").assertIsNotEnabled()
        compose.onNodeWithTag("otp").assertTextEquals("")
    }
    @Test fun manualLanguageSurvivesRecreationAndChangeEmailRetainsCooldown() {
        choose("de")
        compose.activityRule.scenario.recreate(); waitFor("screen_LOGIN")
        compose.onNodeWithTag("language-picker").assertTextContains("German", substring = true)
        compose.onNodeWithTag("login-email").performTextInput("Acceptance.Case@example.com")
        androidx.test.espresso.Espresso.closeSoftKeyboard()
        compose.onNodeWithTag("auth-submit").performScrollTo().performClick(); waitFor("screen_OTP")
        val deadline = model.resendAtMillis
        compose.onNodeWithTag("change-email").performScrollTo().performClick(); waitFor("screen_LOGIN")
        compose.onNodeWithTag("login-email").assertTextEquals("Acceptance.Case@example.com")
        assertEquals(deadline, model.resendAtMillis)
        compose.onNodeWithTag("header-logo").assertIsDisplayed()
    }
}
