package com.prettylisavpn.android

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
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
    @Test fun restoredAccountHasNoFixtureOrVpnActions() {
        launch(); waitFor("live-account")
        compose.onNodeWithTag("account-email").assertTextEquals("acceptance@example.com")
        compose.onNodeWithTag("test-banner").assertDoesNotExist()
        compose.onNodeWithText("connect VPN · unavailable").assertIsNotEnabled()
        compose.activityRule.scenario.recreate(); waitFor("live-account")
        compose.onNodeWithTag("live-banner").assertIsDisplayed()
    }
    @Test fun offlineRestoreIsRetryable() {
        api.failure = "offline"; launch(); waitFor("session-unavailable")
        assertNotNull(vault.value)
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
