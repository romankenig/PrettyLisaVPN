package com.prettylisavpn.android

import androidx.compose.ui.test.*
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import java.io.File
import android.graphics.Bitmap
import com.prettylisavpn.android.auth.*
import com.prettylisavpn.android.data.*
import org.junit.*
import org.junit.Assert.*
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class AuthSessionUiTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()
    private class Vault : CredentialVault {
        var value: Credentials? = Credentials("c21132ac-0d2e-4da7-96ac-8a6ceeb019ba", "synthetic", "2030-01-01T00:00:00Z")
        override fun read() = value
        override fun write(credentials: Credentials) { value = credentials }
        override fun clear() { value = null }
        override fun installationId() = "a1d3475f-0155-49e9-88a9-27125a19b12d"
    }
    private class Api : AuthApi {
        var failure: String? = null
        override suspend fun requestOtp(email: String) = Unit
        override suspend fun verifyOtp(email: String, code: String, installationId: String, deviceName: String) = tokens()
        private fun tokens() = Tokens("synthetic-bearer", 60, Credentials("c21132ac-0d2e-4da7-96ac-8a6ceeb019ba", "rotated-synthetic", "2030-01-01T00:00:00Z"))
        override suspend fun refresh(credentials: Credentials): Tokens { failure?.let { throw AuthFailure(it) }; return tokens() }
        override suspend fun me(access: String): Profile { failure?.let { throw AuthFailure(it) }; return Profile("acceptance@example.com", "Free", 1) }
        override suspend fun logout(access: String) { failure?.let { throw AuthFailure(it) } }
    }
    private lateinit var model: ScreenModel
    private val api = Api()
    private val vault = Vault()
    private fun launch() {
        SourceFactory.sourceForTests = LiveSessionSource(SessionCoordinator(api, vault, "Test Android"))
        compose.runOnUiThread { compose.activity.viewModelStore.clear() }
        compose.activityRule.scenario.recreate()
        compose.runOnUiThread { model = compose.activity.screenModel }
    }
    @After fun reset() { SourceFactory.sourceForTests = null }
    private fun waitFor(tag: String) = compose.waitUntil(10_000) { compose.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty() }
    private fun enter(tag: String, value: String) {
        compose.waitUntil(10_000) { compose.activity.hasWindowFocus() }
        val field = compose.onNodeWithTag(tag).performScrollTo()
        val automation = InstrumentationRegistry.getInstrumentation().uiAutomation
        automation.waitForIdle(500, 5_000)
        field.performTouchInput { click() }
        compose.waitUntil(5_000) { field.fetchSemanticsNode().config.getOrNull(androidx.compose.ui.semantics.SemanticsProperties.Focused) == true }
        compose.waitUntil(10_000) { ViewCompat.getRootWindowInsets(compose.activity.window.decorView)?.isVisible(WindowInsetsCompat.Type.ime()) == true }
        automation.waitForIdle(500, 5_000); field.performTextInput(value); field.assertTextEquals(value)
        automation.waitForIdle(500, 5_000)
        if (ViewCompat.getRootWindowInsets(compose.activity.window.decorView)?.isVisible(WindowInsetsCompat.Type.ime()) == true) androidx.test.espresso.Espresso.closeSoftKeyboard()
        automation.waitForIdle(500, 5_000)
        compose.waitUntil(10_000) { ViewCompat.getRootWindowInsets(compose.activity.window.decorView)?.isVisible(WindowInsetsCompat.Type.ime()) != true }
    }
    private fun screenshot(name: String) {
        compose.waitForIdle()
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        instrumentation.uiAutomation.waitForIdle(500, 5_000)
        val folder = File(instrumentation.targetContext.getExternalFilesDir(null), "acceptance/auth-session")
        check(folder.mkdirs() || folder.isDirectory)
        File(folder, "$name.png").outputStream().use { checkNotNull(instrumentation.uiAutomation.takeScreenshot()).compress(Bitmap.CompressFormat.PNG, 100, it) }
    }
    @Test fun otpFlowAndRecreationNeverSaveCode() {
        vault.value = null; launch(); waitFor("screen_LOGIN")
        enter("login-email", "acceptance@example.com")
        compose.onNodeWithTag("auth-submit").performScrollTo().performClick(); waitFor("screen_OTP")
        enter("otp", "123456")
        compose.activityRule.scenario.recreate(); waitFor("screen_OTP")
        compose.onNodeWithTag("otp").assertTextEquals("")
        enter("otp", "123456")
        compose.onNodeWithTag("auth-submit").performScrollTo().performClick(); waitFor("live-account")
        screenshot("otp-account")
        compose.onNodeWithTag("screen_OTP").assertDoesNotExist()
    }
    @Test fun restoredAccountHasNoFixtureOrVpnActions() {
        launch(); waitFor("live-account")
        compose.onNodeWithTag("account-email").assertTextEquals("acceptance@example.com")
        compose.onNodeWithTag("test-banner").assertDoesNotExist()
        compose.onNodeWithText("connect VPN · unavailable").assertIsNotEnabled()
        compose.activityRule.scenario.recreate(); waitFor("live-account")
        compose.onNodeWithTag("live-banner").assertIsDisplayed()
        screenshot("restored-account")
    }
    @Test fun offlineRestoreIsRetryable() {
        api.failure = "offline"; launch(); waitFor("session-unavailable")
        assertNotNull(vault.value)
        screenshot("offline-restore")
        api.failure = null; compose.onNodeWithTag("restore-retry").performScrollTo().performClick()
        waitFor("live-account")
    }
    @Test fun revokedDeviceRemovesAccountAndCredentials() {
        launch(); waitFor("live-account"); api.failure = "device_revoked"
        compose.onNodeWithTag("account-refresh").performScrollTo().performClick(); waitFor("screen_LOGIN")
        assertNull(vault.value)
        compose.onNodeWithTag("live-account").assertDoesNotExist()
    }
    @Test fun offlineLogoutDoesNotPretendSuccess() {
        launch(); waitFor("live-account"); api.failure = "offline"
        compose.runOnUiThread { model.perform(Command.Logout) }
        compose.waitUntil(5_000) { model.state.value.error != null }
        compose.onNodeWithTag("live-account").assertExists(); assertNotNull(vault.value)
        api.failure = null; compose.runOnUiThread { model.perform(Command.Logout) }; waitFor("screen_LOGIN")
        assertNull(vault.value)
    }
}
