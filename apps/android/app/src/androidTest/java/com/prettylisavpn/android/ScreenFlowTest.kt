package com.prettylisavpn.android

import android.graphics.Bitmap
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import com.prettylisavpn.android.data.Scenario
import org.junit.*
import org.junit.Assert.*
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class ScreenFlowTest {
    @get:Rule val name = org.junit.rules.TestName()
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()
    private var passed = false
    @Before fun ready() { waitFor("brand-logo") }
    @After fun evidenceOnFailure() { if (!passed) runCatching { screenshot("failure-${name.methodName}") } }
    private fun waitFor(tag: String) {
        compose.waitUntil(10_000) { compose.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty() }
        compose.waitForIdle()
    }
    private fun click(tag: String) {
        if (compose.onAllNodes(hasTestTag(tag) and hasAnyAncestor(hasScrollAction())).fetchSemanticsNodes().isNotEmpty()) {
            compose.onNodeWithTag(tag).performScrollTo()
        }
        compose.waitForIdle()
        InstrumentationRegistry.getInstrumentation().uiAutomation.waitForIdle(500, 5_000)
        compose.onNodeWithTag(tag).performClick()
    }
    private fun back() {
        compose.waitForIdle()
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        instrumentation.waitForIdleSync()
        // Fence native Dialog window registration/focus before sending the OS Back action.
        instrumentation.uiAutomation.waitForIdle(300, 5_000)
        check(InstrumentationRegistry.getInstrumentation().uiAutomation.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK))
        instrumentation.waitForIdleSync()
        instrumentation.uiAutomation.waitForIdle(300, 5_000)
        compose.waitForIdle()
    }
    private fun idle() { compose.waitUntil(10_000) { !compose.activity.screenModel.state.value.busy } }
    private fun scenario(value: Scenario) {
        compose.runOnUiThread { compose.activity.screenModel.configure(value) }
    }
    private fun hideKeyboard() {
        // Use the instrumentation IME action; clearing the Android host View focus races
        // Compose's own focus tree on API 26 and can reopen the keyboard.
        androidx.test.espresso.Espresso.closeSoftKeyboard()
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        instrumentation.waitForIdleSync()
        instrumentation.uiAutomation.waitForIdle(500, 5_000)
        compose.waitUntil(10_000) {
            androidx.core.view.ViewCompat.getRootWindowInsets(compose.activity.window.decorView)?.isVisible(WindowInsetsCompat.Type.ime()) != true
        }
    }
    private fun signOut() {
        click("tab_SETTINGS"); click("logout"); click("confirm-dialog"); idle(); waitFor("screen_LOGIN")
    }
    @Test fun authValidationBackAndRecreationClearOtp() {
        scenario(Scenario.SLOW)
        signOut()
        click("auth-submit")
        compose.onNodeWithText("Enter a valid email.").assertExists()
        compose.onNodeWithTag("login-email").performTextInput("test@example.invalid")
        hideKeyboard(); click("auth-submit")
        compose.onNodeWithTag("auth-submit").assertIsNotEnabled()
        compose.onNodeWithTag("login-email").assertIsNotEnabled()
        screenshot("auth-loading")
        waitFor("screen_OTP")
        compose.onNodeWithTag("tab_HOME").assertDoesNotExist()
        compose.onNodeWithTag("otp").performTextInput("000000")
        hideKeyboard(); click("auth-submit"); idle()
        compose.onNodeWithText("Test code expired. Request a new code.").assertExists()
        screenshot("otp-error")
        compose.activityRule.scenario.recreate()
        compose.onNodeWithTag("otp").assertTextEquals("")
        compose.onNodeWithTag("otp-resend").assertIsNotEnabled()
        hideKeyboard()
        back(); waitFor("screen_LOGIN")
        compose.onNodeWithTag("login-email").assertTextEquals("test@example.invalid")
        click("auth-submit"); waitFor("screen_OTP")
        compose.onNodeWithTag("otp").performTextInput("123456")
        hideKeyboard(); click("auth-submit"); idle(); waitFor("message-dialog")
        back(); waitFor("brand-logo")
        compose.onNodeWithTag("screen_LOGIN").assertDoesNotExist()
        compose.onNodeWithTag("test-banner").assertIsDisplayed()
        passed = true
    }
    @Test fun countryEntitlementsSimulationAndDialogBack() {
        scenario(Scenario.FREE); waitFor("brand-logo")
        click("open-countries"); waitFor("country-DE")
        compose.onNodeWithTag("country-DE").assertIsNotEnabled()
        compose.onNodeWithTag("country-AUTO").assertIsEnabled()
        back(); waitFor("brand-logo")
        scenario(Scenario.SLOW); waitFor("brand-logo")
        click("open-countries"); waitFor("country-DE")
        compose.onNodeWithTag("country-search").performTextInput("zzzz")
        compose.onNodeWithTag("countries-empty").assertExists()
        compose.onNodeWithTag("country-search").performTextReplacement("")
        hideKeyboard(); click("country-DE"); idle(); waitFor("brand-logo")
        click("connect"); compose.onNodeWithTag("connect").assertIsNotEnabled(); idle()
        compose.onNodeWithTag("connection-status").assertTextEquals("SIMULATION ACTIVE — NOT A VPN")
        click("connection-details"); compose.onNodeWithText("simulated connection").assertExists()
        screenshot("connection-details"); back()
        compose.onNodeWithTag("connection-status").assertTextEquals("SIMULATION ACTIVE — NOT A VPN")
        click("connect"); idle()
        compose.onNodeWithTag("connection-status").assertTextEquals("not connected")
        passed = true
    }
    @Test fun deviceDialogCancelFailureRetryAndHomeRefresh() {
        click("tab_SETTINGS"); click("open-devices"); waitFor("revoke-2")
        compose.onNodeWithText("Last login: no data").assertExists()
        click("revoke-2"); compose.onNodeWithTag("confirmation-dialog").assertIsDisplayed(); back()
        compose.onNodeWithTag("revoke-2").assertIsEnabled()
        scenario(Scenario.FAIL_NEXT)
        click("revoke-2"); click("confirm-dialog"); idle()
        compose.onNodeWithTag("confirmation-dialog").assertExists()
        compose.onNodeWithTag("operation-error").assertExists()
        screenshot("device-failure")
        click("confirm-dialog"); idle()
        compose.onNodeWithTag("revoke-2").assertIsNotEnabled()
        screenshot("devices")
        back(); compose.onNodeWithTag("screen_SETTINGS").assertIsDisplayed()
        back(); waitFor("brand-logo")
        compose.onNodeWithTag("device-count").assertTextEquals("Active devices: 1 / 5")
        passed = true
    }
    @Test fun currentDeviceRevocationRemovesProtectedScreens() {
        click("tab_SETTINGS"); click("open-devices"); waitFor("revoke-1")
        click("revoke-1"); click("confirm-dialog"); idle(); waitFor("screen_LOGIN")
        compose.onNodeWithTag("tab_SETTINGS").assertDoesNotExist()
        compose.onNodeWithTag("screen_DEVICES").assertDoesNotExist()
        passed = true
    }
    @Test fun paymentCapabilitiesPendingAndCancellationPreserveAccess() {
        scenario(Scenario.PAYMENT_PENDING); waitFor("brand-logo")
        val before = compose.activity.screenModel.state.value.data.paidUntil
        click("tab_SETTINGS"); click("open-subscription"); waitFor("open-payment")
        click("open-payment"); click("currency-USD")
        compose.onNodeWithTag("route-MIR").assertIsNotEnabled()
        click("route-CRYPTO")
        compose.onNodeWithTag("recurring-terms").assertTextEquals("One-time test payment; no automatic charges.")
        click("currency-RUB"); screenshot("payment-routes")
        click("simulate-payment"); idle(); waitFor("screen_SUBSCRIPTION")
        assertEquals(before, compose.activity.screenModel.state.value.data.paidUntil)
        compose.onNodeWithTag("payment-pending").assertExists()
        click("confirm-payment"); idle()
        assertNotEquals(before, compose.activity.screenModel.state.value.data.paidUntil)
        val after = compose.activity.screenModel.state.value.data.paidUntil
        click("cancel-subscription"); screenshot("cancel-dialog"); back()
        assertTrue(compose.activity.screenModel.state.value.data.autoRenew)
        click("cancel-subscription"); click("confirm-dialog"); idle()
        if (compose.activity.screenModel.state.value.data.paymentPending) { click("confirm-payment"); idle() }
        assertEquals(after, compose.activity.screenModel.state.value.data.paidUntil)
        assertFalse(compose.activity.screenModel.state.value.data.autoRenew)
        passed = true
    }
    @Test fun supportDraftBackFailureReceiptAndAttachmentLimit() {
        scenario(Scenario.SLOW)
        click("tab_ABOUT"); click("open-support")
        click("support-subject"); compose.onNodeWithTag("support-subject").performTextInput("Test issue")
        compose.onNodeWithTag("support-description").performScrollTo().performTextInput("Synthetic description")
        compose.onNodeWithTag("support-email").performScrollTo().performTextInput("test@example.invalid")
        hideKeyboard()
        repeat(3) { click("support-attach") }
        compose.onNodeWithTag("support-attach").assertIsNotEnabled()
        hideKeyboard()
        back(); compose.onNodeWithTag("confirmation-dialog").assertExists(); back()
        compose.onNodeWithTag("support-subject").assertTextEquals("Test issue")
        scenario(Scenario.FAIL_NEXT)
        click("support-send")
        compose.onNodeWithTag("support-email").assertIsNotEnabled()
        idle(); compose.onNodeWithTag("operation-error").assertExists()
        click("support-send"); idle(); waitFor("support-receipt")
        screenshot("support-receipt")
        click("support-status"); idle()
        compose.onNodeWithText("Simulated delivery complete — no email was sent.").assertExists()
        back(); compose.onNodeWithTag("screen_ABOUT").assertIsDisplayed()
        passed = true
    }
    @Test fun messageLaterDoesNotAcknowledgeAndFailureDoesNotNavigate() {
        click("home-messages"); waitFor("message-dialog"); back()
        assertEquals(2, compose.activity.screenModel.state.value.data.messages.size)
        click("home-messages"); scenario(Scenario.FAIL_NEXT)
        click("message-action"); idle()
        compose.onNodeWithTag("operation-error").assertExists()
        compose.onNodeWithTag("screen_SUBSCRIPTION").assertDoesNotExist()
        screenshot("message-error")
        click("message-action"); idle(); waitFor("screen_SUBSCRIPTION")
        assertEquals(1, compose.activity.screenModel.state.value.data.messages.size)
        back(); waitFor("brand-logo")
        passed = true
    }
    @Test fun loadingErrorRetryEmptyAndStaleStayDistinct() {
        scenario(Scenario.OFFLINE)
        waitFor("retry-HOME")
        screenshot("offline")
        scenario(Scenario.STANDARD); waitFor("brand-logo")
        scenario(Scenario.STALE); waitFor("brand-logo")
        compose.onNodeWithTag("stale-notice").assertExists()
        compose.onNodeWithTag("connect").performScrollTo().assertIsNotEnabled()
        scenario(Scenario.EMPTY); waitFor("brand-logo")
        click("tab_SETTINGS"); click("open-devices"); waitFor("empty-devices")
        screenshot("empty-devices")
        back(); back(); waitFor("brand-logo")
        passed = true
    }
    @Test fun latePaymentResultDoesNotPopTheParentPage() {
        scenario(Scenario.SLOW); waitFor("brand-logo")
        click("tab_SETTINGS"); click("open-subscription"); waitFor("open-payment")
        val before = compose.activity.screenModel.state.value.data.paidUntil
        click("open-payment"); click("simulate-payment")
        compose.onNodeWithTag("simulate-payment").assertIsNotEnabled()
        compose.onNodeWithTag("currency-USD").assertIsNotEnabled()
        back(); waitFor("screen_SUBSCRIPTION")
        idle()
        compose.onNodeWithTag("screen_SUBSCRIPTION").assertIsDisplayed()
        assertNotEquals(before, compose.activity.screenModel.state.value.data.paidUntil)
        passed = true
    }
    private fun screenshot(name: String) {
        compose.waitForIdle()
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        instrumentation.waitForIdleSync()
        instrumentation.uiAutomation.waitForIdle(250, 5_000)
        val directory = File(instrumentation.targetContext.getExternalFilesDir(null), "acceptance/flows")
        check(directory.mkdirs() || directory.isDirectory)
        val bitmap = checkNotNull(instrumentation.uiAutomation.takeScreenshot())
        try { File(directory, "$name.png").outputStream().use { check(bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)) } }
        finally { bitmap.recycle() }
    }
}
