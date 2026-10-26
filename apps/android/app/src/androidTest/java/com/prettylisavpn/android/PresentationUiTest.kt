package com.prettylisavpn.android

import androidx.activity.compose.setContent
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
import com.prettylisavpn.android.vpn.*
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
    @Test fun connectionNoticeIsVisibleOfflineAndDisappearsOnRecovery() {
        val connected=androidx.compose.runtime.mutableStateOf<Boolean?>(null)
        compose.runOnUiThread { compose.activity.setContent {
            PrettyLisaTheme { LocalizedApp { ConnectionNotice(connected.value) } }
        } }
        compose.onNodeWithTag("server-connection-notice").assertDoesNotExist()
        compose.runOnUiThread { connected.value=false }
        compose.onNodeWithTag("server-connection-notice").assertTextEquals("no connection to the server, check your internet connection")
        compose.runOnUiThread { connected.value=true }
        compose.onNodeWithTag("server-connection-notice").assertDoesNotExist()
    }
    @Test fun vpnAttemptCommentsFollowTheCurrentAttemptAndDisappearOnSuccess() {
        val state = kotlinx.coroutines.flow.MutableStateFlow(VpnStatus(VpnPhase.CONNECTING, attempt = VpnAttempt(VpnMethod("wireguard", "WireGuard"))))
        val actions = object : VpnActions {
            override val status = state
            override fun connect(country: String) {}
            override fun disconnect() {}
        }
        compose.runOnUiThread { compose.activity.setContent {
            PrettyLisaTheme { LocalizedApp { androidx.compose.foundation.layout.Column { VpnControls(actions, "DE", true) } } }
        } }
        compose.onNodeWithTag("vpn-attempt").assertTextEquals("trying WireGuard…")
        screenshot("vpn-trying-en")
        compose.runOnUiThread { state.value = VpnStatus(VpnPhase.CONNECTING, attempt = VpnAttempt(VpnMethod("wireguard", "WireGuard"), VpnMethod("wireguard", "WireGuard"))) }
        compose.onNodeWithTag("vpn-attempt").assertTextEquals("WireGuard did not connect. trying WireGuard…")
        screenshot("vpn-retrying-en")
        compose.runOnUiThread { state.value = VpnStatus(VpnPhase.CONNECTING, attempt = VpnAttempt(VpnMethod("wireguard", "WireGuard"))) }
        compose.onNodeWithTag("vpn-attempt").assertTextEquals("trying WireGuard…")
        screenshot("vpn-verifying-en")
        compose.runOnUiThread { state.value = VpnStatus(VpnPhase.CONNECTING, attempt = VpnAttempt(VpnMethod("vless", "VLESS"), VpnMethod("wireguard", "WireGuard"))) }
        compose.onNodeWithTag("vpn-attempt").assertTextEquals("WireGuard did not connect. trying VLESS…")
        compose.runOnUiThread { state.value = VpnStatus(VpnPhase.CONNECTING, attempt = VpnAttempt(VpnMethod("vless", "VLESS"), VpnMethod("wireguard", "WireGuard"))) }
        compose.onNodeWithTag("vpn-attempt").assertTextEquals("WireGuard did not connect. trying VLESS…")
        screenshot("vpn-switch-verifying-en")
        compose.onNodeWithTag("vpn-method").assertDoesNotExist()
        compose.runOnUiThread { state.value = VpnStatus(VpnPhase.CONNECTED, method = VpnMethod("wireguard", "WireGuard")) }
        compose.onNodeWithTag("vpn-method").assertTextEquals("WireGuard")
        compose.onNodeWithTag("vpn-attempt").assertDoesNotExist()
        compose.runOnUiThread { state.value = VpnStatus(VpnPhase.FAILED, error = VpnError.METHODS_EXHAUSTED, method = VpnMethod("hysteria", "Hysteria / Hysteria 2")) }
        compose.onNodeWithTag("vpn-attempt").assertDoesNotExist()
        compose.onNodeWithTag("vpn-error").assertTextContains("all methods tried", substring = true)
        screenshot("vpn-failed-diagnostic-en")
        compose.runOnUiThread { state.value = VpnStatus(VpnPhase.DISCONNECTED) }
        compose.onNodeWithTag("vpn-diagnostic").assertDoesNotExist()
    }
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
            val flag = compose.onNodeWithTag("language-flag-${language.code}", useUnmergedTree = true).getUnclippedBoundsInRoot()
            assertTrue("Flag/name gap is too wide", english.left.value - flag.right.value in 4f..20f)
            compose.onNodeWithTag("header-mark").assertWidthIsAtLeast(androidx.compose.ui.unit.Dp(44f))
            compose.onNodeWithTag("component-versions").assertTextContains(BuildConfig.VERSION_NAME, substring = true)
            compose.onNodeWithTag("component-versions").assert(hasAnyAncestor(hasTestTag("app-version-footer")))
            compose.onAllNodes(hasTestTag("component-versions") and hasAnyAncestor(hasTestTag("app-header"))).assertCountEquals(0)
            val footer = compose.onNodeWithTag("app-version-footer").getUnclippedBoundsInRoot()
            assertEquals(compose.onNodeWithTag("app-root").getUnclippedBoundsInRoot().bottom.value, footer.bottom.value, 1f)
            assertTrue(footer.top > compose.onNodeWithTag("app-header").getUnclippedBoundsInRoot().bottom)
            compose.onNodeWithTag("live-banner").assertDoesNotExist()
            screenshot("login-${language.code}")
        }
        compose.onNodeWithTag("language-picker").performClick()
        val nodes = AppLanguage.entries.map { compose.onNodeWithTag("language-${it.code}").getUnclippedBoundsInRoot().top.value }
        assertEquals(nodes.sorted(), nodes)
        screenshot("language-menu")
    }
    @Test fun otpLinksKeepSixtySecondCooldownAndCodeDuringLanguageChanges() {
        compose.onNodeWithTag("login-email").performTextInput("Acceptance.Case@example.com")
        androidx.test.espresso.Espresso.closeSoftKeyboard()
        compose.onNodeWithTag("auth-submit").performScrollTo().performClick(); waitFor("screen_OTP")
        compose.onNodeWithTag("app-version-footer").assertIsDisplayed()
        val deadline = model.resendAtMillis
        assertTrue("OTP must wait a full minute", deadline - SystemClock.elapsedRealtime() > 50_000)
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
        assertEquals("Compact links should share a row at the default font size", resend, change, 1f)
        val links = compose.onNodeWithTag("otp-links").getUnclippedBoundsInRoot()
        assertTrue("OTP links must not reserve two button rows", links.bottom.value - links.top.value <= 56f)
        val field = compose.onNodeWithTag("otp").getUnclippedBoundsInRoot()
        assertTrue("OTP secondary area including both gaps must fit 56dp", submit - field.bottom.value <= 57f)
        compose.onNodeWithTag("auth-submit").performScrollTo().assertIsDisplayed()
        screenshot("otp-ru")
        compose.waitUntil(65_000) { SystemClock.elapsedRealtime() >= deadline + 300 }
        compose.onNodeWithTag("otp-resend").assertIsEnabled()
        screenshot("otp-ready-ru")
        compose.onNodeWithTag("otp-resend").performClick()
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
