package com.prettylisavpn.android

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.prettylisavpn.android.auth.*
import com.prettylisavpn.android.data.*
import java.io.File
import android.graphics.Bitmap
import org.junit.*
import org.junit.Assert.*
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class AccountScreensTest {
    @get:Rule val compose=createAndroidComposeRule<MainActivity>()
    private val owner="30000000-0000-0000-0000-000000000001"
    private val device="30000000-0000-0000-0000-000000000002"
    private val message="30000000-0000-0000-0000-000000000003"
    private var mode="DISABLED"
    private var revision="r1"
    private var active=true
    private var ackFail=false
    private var messages=true
    private var starts=0
    private var sends=0
    private var receipt:SupportReceipt?=null
    private lateinit var model:ScreenModel
    private val api=object:AuthApi {
        override suspend fun requestOtp(email:String)=Unit
        override suspend fun verifyOtp(email:String,code:String,installationId:String,deviceName:String)=tokens()
        fun tokens()=Tokens("fake",900,Credentials(device,"fake","2030-01-01T00:00:00Z"))
        override suspend fun refresh(credentials:Credentials)=tokens()
        override suspend fun me(access:String)=Profile("screens@example.com","Premium",if(active)2 else 1,owner)
        override suspend fun logout(access:String)=Unit
    }
    private val accounts=object:AccountApi {
        override suspend fun devices(token:String)=listOf(Device(device,"Test phone",false,"2026-10-20T00:00:00Z",null,active))
        override suspend fun revoke(token:String,id:String):Device { active=false;return devices(token).single() }
        override suspend fun messages(token:String)=if(messages)listOf(AccountMessage(message,2,"Account notice","Synthetic test message","SUBSCRIPTION"))else emptyList()
        override suspend fun acknowledge(token:String,id:String,revision:Int) { if(ackFail)throw AuthFailure("offline");messages=false }
        override suspend fun overview(token:String)=BillingOverview(revision,mode,true,"PREMIUM","ACTIVE","2030-01-01T00:00:00Z",true,"Test card","RUB 100.00",routeIds.map { PaymentRoute(it,it,setOf("RUB","USD"),emptySet()) },emptyList(),billingActions,null)
        override suspend fun start(token:String,intent:BillingIntent):OperationReceipt { starts++;return OperationReceipt(device,"PENDING") }
        override suspend fun operation(token:String,id:String)=OperationReceipt(id,"PENDING")
        override suspend fun supportStatus(token:String,id:String)=receipt
        override suspend fun supportSubmit(token:String,report:SupportSubmission):SupportReceipt { sends++;return SupportReceipt(report.requestId,"ACCEPTED").also { receipt=it } }
    }
    @Before fun launch() {
        val vault=object:CredentialVault {
            var value:Credentials?=Credentials(device,"fake","2030-01-01T00:00:00Z")
            override fun read()=value
            override fun write(credentials:Credentials) { value=credentials }
            override fun clear() { value=null }
            override fun installationId()=owner
        }
        val instrumentation=InstrumentationRegistry.getInstrumentation()
        compose.waitForIdle();instrumentation.waitForIdleSync();instrumentation.uiAutomation.waitForIdle(500,5_000)
        compose.waitUntil(10_000) { compose.activity.hasWindowFocus() }
        SourceFactory.sourceForTests=LiveSessionSource(SessionCoordinator(api,vault,"Test"),accounts)
        compose.runOnUiThread { compose.activity.viewModelStore.clear() };compose.activityRule.scenario.recreate()
        compose.runOnUiThread { model=compose.activity.screenModel };waitFor("live-account")
    }
    @After fun reset() { SourceFactory.sourceForTests=null }
    private fun waitFor(tag:String)=compose.waitUntil(10_000) { compose.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty() }
    private fun click(tag:String) {
        if(compose.onAllNodes(hasTestTag(tag) and hasAnyAncestor(hasScrollAction())).fetchSemanticsNodes().isNotEmpty()) compose.onNodeWithTag(tag).performScrollTo()
        compose.waitForIdle();InstrumentationRegistry.getInstrumentation().uiAutomation.waitForIdle(300,5000)
        compose.onNodeWithTag(tag).performClick()
    }
    private fun idle()=compose.waitUntil(10_000) { !model.state.value.busy }
    private fun screenshot(name:String) {
        compose.waitForIdle();val i=InstrumentationRegistry.getInstrumentation();i.uiAutomation.waitForIdle(500,5000)
        val dir=File(i.targetContext.getExternalFilesDir(null),"acceptance/account-api");check(dir.mkdirs()||dir.isDirectory)
        File(dir,"$name.png").outputStream().use { checkNotNull(i.uiAutomation.takeScreenshot()).compress(Bitmap.CompressFormat.PNG,100,it) }
    }
    @Test fun devicesRevokeUpdatesHomeAndBack() {
        click("live-devices");waitFor("live-revoke-$device");click("live-revoke-$device");click("confirm-dialog");idle()
        compose.onNodeWithText("revoked").assertExists();screenshot("devices-revoked")
        compose.runOnUiThread { compose.activity.onBackPressedDispatcher.onBackPressed() };waitFor("live-account")
        compose.onNodeWithText("active devices: 1 / 5").assertExists()
    }
    @Test fun messagesOnlyNavigateAfterSuccessfulAck() {
        click("live-messages");waitFor("message-action-$message");ackFail=true;click("message-action-$message");idle()
        compose.onNodeWithTag("live-messages-screen").assertExists();assertTrue(messages)
        ackFail=false;click("message-action-$message");waitFor("provider-mode");assertFalse(messages)
    }
    @Test fun disabledAndSandboxActionsRemainDisabled() {
        click("live-subscription");waitFor("provider-mode")
        for(kind in billingActions)compose.onNodeWithTag("live-pay-$kind").assertIsNotEnabled()
        mode="SANDBOX";click("live-refresh-BILLING");compose.waitUntil(10_000) { model.state.value.data.billing?.mode=="SANDBOX" }
        for(kind in billingActions)compose.onNodeWithTag("live-pay-$kind").assertIsNotEnabled()
        assertEquals(0,starts);screenshot("sandbox-read-only")
    }
    @Test fun changedPriceClosesConfirmationWithoutPosting() {
        mode="LIVE";click("live-subscription");waitFor("provider-mode")
        click("live-pay-CANCEL");waitFor("confirmation-dialog");revision="r2"
        click("confirm-dialog");idle()
        compose.waitUntil(10_000) { compose.onAllNodesWithTag("confirmation-dialog").fetchSemanticsNodes().isEmpty() }
        assertEquals(0,starts)
    }
    @Test fun supportAcceptedReceiptSurvivesRecreationWithoutResending() {
        click("live-support");waitFor("live-support-screen")
        compose.runOnUiThread { model.perform(Command.Support(device,"Synthetic test","No real email","reply@example.com",0)) };idle();waitFor("live-support-receipt")
        compose.activityRule.scenario.recreate();waitFor("live-support-receipt");assertEquals(1,sends)
        click("live-support-status");idle();assertEquals(1,sends);screenshot("support-accepted")
    }
    @Test fun supportDraftBackRequiresConfirmation() {
        click("live-support");waitFor("live-support-screen")
        // A test-only semantics edit; the real platform picker remains user initiated.
        val field=compose.onNodeWithTag("live-support-subject").performScrollTo()
        compose.waitUntil(10_000) { compose.activity.hasWindowFocus() }
        field.performTouchInput { click() }
        compose.waitUntil(10_000) { androidx.core.view.ViewCompat.getRootWindowInsets(compose.activity.window.decorView)?.isVisible(androidx.core.view.WindowInsetsCompat.Type.ime())==true }
        InstrumentationRegistry.getInstrumentation().uiAutomation.waitForIdle(500,5000)
        field.performTextInput("Draft");field.assertTextEquals("Draft")
        androidx.test.espresso.Espresso.closeSoftKeyboard()
        InstrumentationRegistry.getInstrumentation().uiAutomation.waitForIdle(500,5000)
        compose.runOnUiThread { compose.activity.onBackPressedDispatcher.onBackPressed() };waitFor("confirmation-dialog")
        click("dismiss-dialog");compose.onNodeWithTag("live-support-screen").assertExists();assertEquals(0,sends)
    }
}
