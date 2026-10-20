package com.prettylisavpn.android

import android.graphics.Bitmap
import androidx.core.content.edit
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
    private fun screenshot(name: String) {
        compose.waitForIdle()
        val i = InstrumentationRegistry.getInstrumentation()
        i.uiAutomation.waitForIdle(500, 5_000)
        val dir = File(i.targetContext.getExternalFilesDir(null), "acceptance/ui-polish")
        check(dir.mkdirs() || dir.isDirectory)
        File(dir, "$name.png").outputStream().use { checkNotNull(i.uiAutomation.takeScreenshot()).compress(Bitmap.CompressFormat.PNG, 100, it) }
    }
    @Test fun allSixLanguagesTranslateLoginAndPreserveBrandAndDraft() {
        compose.onNodeWithTag("login-email").performTextInput("acceptance@example.com")
        androidx.test.espresso.Espresso.closeSoftKeyboard()
        for (language in AppLanguage.entries) {
            choose(language.code)
            compose.onNodeWithTag("header-logo").assertTextEquals("PrettyLisaVPN")
            compose.onNodeWithTag("login-email").assertTextEquals("acceptance@example.com")
            val localized = compose.activity.createConfigurationContext(android.content.res.Configuration(compose.activity.resources.configuration).apply { setLocale(Locale.forLanguageTag(language.code)) })
            compose.onNodeWithText(localized.getString(R.string.ui_sign_in_by_email)).assertExists()
            compose.onNodeWithTag("component-versions").assertTextContains("0.6.0", substring = true)
            compose.onNodeWithTag("live-banner").assertDoesNotExist()
            screenshot("login-${language.code}")
        }
        compose.onNodeWithTag("language-picker").performClick()
        val nodes = AppLanguage.entries.map { compose.onNodeWithTag("language-${it.code}").fetchSemanticsNode().boundsInRoot.top }
        assertEquals(nodes.sorted(), nodes)
        screenshot("language-menu")
    }
    @Test fun otpLinksKeepThirtySecondCooldownAndCodeDuringLanguageChanges() {
        compose.onNodeWithTag("login-email").performTextInput("acceptance@example.com")
        androidx.test.espresso.Espresso.closeSoftKeyboard()
        compose.onNodeWithTag("auth-submit").performScrollTo().performClick(); waitFor("screen_OTP")
        val deadline = model.resendAtMillis
        compose.onNodeWithTag("otp-resend").performScrollTo().assertIsNotEnabled()
        compose.onNodeWithTag("otp").performScrollTo().performTextInput("123456")
        androidx.test.espresso.Espresso.closeSoftKeyboard()
        choose("ru")
        assertEquals(deadline, model.resendAtMillis)
        compose.onNodeWithTag("otp").assertTextEquals("123456")
        compose.onNodeWithTag("otp-resend").performScrollTo().assertIsNotEnabled()
        val resend = compose.onNodeWithTag("otp-resend").fetchSemanticsNode().boundsInRoot.top
        val change = compose.onNodeWithTag("change-email").fetchSemanticsNode().boundsInRoot.top
        val submit = compose.onNodeWithTag("auth-submit").fetchSemanticsNode().boundsInRoot.top
        assertTrue(resend < submit && change < submit)
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
        compose.onNodeWithTag("login-email").performTextInput("acceptance@example.com")
        androidx.test.espresso.Espresso.closeSoftKeyboard()
        compose.onNodeWithTag("auth-submit").performScrollTo().performClick(); waitFor("screen_OTP")
        val deadline = model.resendAtMillis
        compose.onNodeWithTag("change-email").performScrollTo().performClick(); waitFor("screen_LOGIN")
        compose.onNodeWithTag("login-email").assertTextEquals("acceptance@example.com")
        assertEquals(deadline, model.resendAtMillis)
        compose.onNodeWithTag("header-logo").assertIsDisplayed()
    }
}
