package com.prettylisavpn.android

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.prettylisavpn.android.auth.*
import com.prettylisavpn.android.data.*
import java.io.File
import android.graphics.Bitmap
import androidx.activity.compose.setContent
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
    private var deviceReads=0
    private var uploadGate:kotlinx.coroutines.CompletableDeferred<Unit>?=null
    private var submitted:SupportSubmission?=null
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
        override suspend fun devices(token:String): List<Device> { deviceReads++; return listOf(Device(device,"Test phone",false,"2026-10-20T00:00:00Z",null,active)) }
        override suspend fun revoke(token:String,id:String):Device { active=false;return devices(token).single() }
        override suspend fun countries(token:String)=listOf(Country("DE","DE","80",true),Country("FR","FR","60",true))
        override suspend fun messages(token:String)=if(messages)listOf(AccountMessage(message,2,"Account notice","Synthetic test message","SUBSCRIPTION"))else emptyList()
        override suspend fun acknowledge(token:String,id:String,revision:Int) { if(ackFail)throw AuthFailure("offline");messages=false }
        override suspend fun overview(token:String)=BillingOverview(revision,mode,true,"PREMIUM","ACTIVE","2030-01-01T00:00:00Z",true,"Test card","RUB 100.00",routeIds.map { PaymentRoute(it,it,setOf("RUB","USD"),emptySet()) },emptyList(),billingActions,null)
        override suspend fun start(token:String,intent:BillingIntent):OperationReceipt { starts++;return OperationReceipt(device,"PENDING") }
        override suspend fun operation(token:String,id:String)=OperationReceipt(id,"PENDING")
        override suspend fun supportStatus(token:String,id:String)=receipt
        override suspend fun supportSubmit(token:String,report:SupportSubmission,progress:(Long,Long)->Unit):SupportReceipt {
            progress(50,100);uploadGate?.await();return supportSubmit(token,report)
        }
        override suspend fun supportSubmit(token:String,report:SupportSubmission):SupportReceipt { submitted=report;sends++;return SupportReceipt(report.requestId,"ACCEPTED").also { receipt=it } }
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
        SourceFactory.sourceForTests=LiveSessionSource(SessionCoordinator(api,vault,"Test"),accounts,uploads={ readSupportImages(instrumentation.targetContext,it) })
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
        click("tab_SETTINGS");screenshot("settings-windows");click("settings-devices");waitFor("live-revoke-$device")
        compose.onNodeWithTag("live-refresh-DEVICES").assertDoesNotExist()
        compose.onNodeWithText("2026-10-20T00:00:00Z", substring=true).assertDoesNotExist()
        val reads=deviceReads
        compose.onNodeWithTag("live-devices-screen").performTouchInput { swipeDown() }
        compose.waitUntil(10_000) { deviceReads>reads && model.state.value.loads[Area.DEVICES]?.phase==LoadPhase.READY }
        val afterDown=deviceReads
        compose.onNodeWithTag("live-devices-screen").performTouchInput { swipeUp() }
        compose.waitUntil(10_000) { deviceReads>afterDown && model.state.value.loads[Area.DEVICES]?.phase==LoadPhase.READY }
        screenshot("devices-readable")
        click("live-revoke-$device");click("confirm-dialog");idle()
        compose.onNodeWithText("revoked").assertExists();screenshot("devices-revoked")
        compose.runOnUiThread { compose.activity.onBackPressedDispatcher.onBackPressed() };waitFor("live-settings")
        click("tab_HOME");compose.onNodeWithText("1 / 5").assertExists()
    }
    @Test fun messagesOnlyNavigateAfterSuccessfulAck() {
        click("tab_SETTINGS");click("settings-messages");waitFor("message-action-$message");ackFail=true;click("message-action-$message");idle()
        compose.onNodeWithTag("live-messages-screen").assertExists();assertTrue(messages)
        ackFail=false;click("message-action-$message");waitFor("provider-mode");assertFalse(messages)
    }
    @Test fun disabledAndSandboxActionsRemainDisabled() {
        click("tab_SETTINGS");click("settings-subscription");waitFor("provider-mode")
        for(kind in billingActions)compose.onNodeWithTag("live-pay-$kind").assertIsNotEnabled()
        mode="SANDBOX";click("live-refresh-BILLING");compose.waitUntil(10_000) { model.state.value.data.billing?.mode=="SANDBOX" }
        for(kind in billingActions)compose.onNodeWithTag("live-pay-$kind").assertIsNotEnabled()
        assertEquals(0,starts);screenshot("sandbox-read-only")
    }
    @Test fun changedPriceClosesConfirmationWithoutPosting() {
        mode="LIVE";click("tab_SETTINGS");click("settings-subscription");waitFor("provider-mode")
        click("live-pay-CANCEL");waitFor("confirmation-dialog");revision="r2"
        click("confirm-dialog");idle()
        compose.waitUntil(10_000) { compose.onAllNodesWithTag("confirmation-dialog").fetchSemanticsNodes().isEmpty() }
        assertEquals(0,starts)
    }
    @Test fun supportAcceptedReceiptSurvivesRecreationWithoutResending() {
        click("tab_ABOUT");click("about-support");waitFor("live-support-screen")
        compose.runOnUiThread { model.perform(Command.Support(device,"Synthetic test","No real email","reply@example.com",0)) };idle();waitFor("live-support-receipt")
        compose.activityRule.scenario.recreate();waitFor("live-support-receipt");assertEquals(1,sends)
        click("live-support-status");idle();assertEquals(1,sends);screenshot("support-accepted")
    }
    @Test fun supportDraftBackRequiresConfirmation() {
        click("tab_ABOUT");waitFor("live-about")
        compose.onNodeWithTag("about-frontend-version").assertTextEquals(BuildConfig.VERSION_NAME)
        compose.onNodeWithTag("about-backend-version").assertTextEquals(compose.activity.getString(R.string.unavailable))
        compose.onNodeWithTag("about-faq-title").assertTextEquals("faq")
        compose.onNodeWithTag("build-source").assertDoesNotExist()
        compose.onNodeWithTag("about-dedication").performScrollTo().assertTextEquals("inspired by love of my life, Lisa")
        screenshot("about-windows-content")
        click("about-support");waitFor("live-support-screen")
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
    @Test fun homeMatchesWindowsAndConnectRemainsOnlyAPreview() {
        compose.onNodeWithTag("account-email").assertTextEquals("screens@example.com")
        for(tag in listOf("live-devices","live-subscription","live-messages","live-support","account-refresh","live-logout")) compose.onNodeWithTag(tag).assertDoesNotExist()
        screenshot("home-account-summary")
        click("home-connect")
        assertFalse(model.state.value.data.simulatedConnection)
        assertEquals(0,starts)
        click("home-manual");click("home-country")
        compose.waitUntil(10_000) { model.state.value.data.countries.size==2 }
        click("home-country-DE")
        compose.onNodeWithTag("home-country").assertTextContains("Germany", substring=true)
        screenshot("home-windows-connection")
        compose.onNodeWithTag("home-network").performScrollTo();screenshot("home-current-network")
    }

    @Test fun supportPreparesNamedAttachmentAndRemovesItWithACross() {
        val uri="content://com.prettylisavpn.android.test.images/sample"
        val info=kotlinx.coroutines.runBlocking { supportImageInfo(compose.activity,uri) }
        assertEquals("test-screen.png",info.name)
        val draft=androidx.lifecycle.SavedStateHandle(mapOf("subject" to "Synthetic report", "description" to "No email will be sent", "selected" to arrayListOf("content://com.prettylisavpn.android.test.images/sample")))
        compose.runOnUiThread {
            compose.activity.setContent {
                com.prettylisavpn.android.ui.PrettyLisaTheme {
                    com.prettylisavpn.android.ui.LocalizedApp {
                        androidx.compose.foundation.layout.Column {
                            com.prettylisavpn.android.ui.AppHeader(false)
                            androidx.compose.foundation.layout.Box(androidx.compose.ui.Modifier.weight(1f)) {
                                com.prettylisavpn.android.ui.LiveSupport(model,draft) {}
                            }
                            com.prettylisavpn.android.ui.AppVersionFooter()
                        }
                    }
                }
            }
        }
        waitFor("support-image-0")
        compose.waitUntil(10_000) { compose.onAllNodesWithText("test-screen.png").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("support-image-0").performScrollTo()
        compose.onNodeWithText("test-screen.png").assertExists()
        compose.onNodeWithText("ready to send",substring=true).assertExists()
        screenshot("support-named-attachment")
        click("support-diagnostics")
        compose.onNodeWithTag("support-diagnostics").assertIsOn()
        compose.onNodeWithText("technical diagnostics are unavailable for Android.").assertDoesNotExist()
        compose.onNodeWithText("done").assertDoesNotExist()
        val report=androidDiagnostics(compose.activity,"0.10.0","en","PREMIUM")
        val json=com.google.gson.JsonParser.parseString(report).asJsonObject
        assertEquals("ANDROID",json.get("platform").asString)
        assertFalse(report.contains("screens@example.com"));assertFalse(report.contains(device));assertFalse(report.contains("fake"))
        click("support-remove-0")
        compose.onNodeWithTag("support-image-0").assertDoesNotExist()
        assertEquals(0,sends)
        compose.runOnUiThread { draft["selected"]=arrayListOf(uri) }
        compose.waitUntil(10_000) { compose.onAllNodesWithText("ready to send",substring=true).fetchSemanticsNodes().isNotEmpty() }
        uploadGate=kotlinx.coroutines.CompletableDeferred()
        try {
            click("live-support-send")
            compose.waitUntil(10_000) { model.state.value.busy && compose.onAllNodesWithText("sending: 50%").fetchSemanticsNodes().isNotEmpty() }
            compose.onNodeWithTag("support-remove-0").assertIsNotEnabled()
            compose.runOnUiThread { compose.activity.onBackPressedDispatcher.onBackPressed() }
            compose.onNodeWithTag("confirmation-dialog").assertDoesNotExist()
            compose.onNodeWithTag("live-support-screen").assertExists()
            screenshot("support-upload-progress")
        } finally { uploadGate?.complete(Unit) }
        waitFor("live-support-receipt");idle()
        assertEquals(1,sends)
        assertEquals(1,submitted!!.uploads.size)
        assertTrue(submitted!!.description.contains("Android diagnostics"));assertTrue(submitted!!.description.contains("ANDROID"))
        compose.onNodeWithText("done").assertDoesNotExist()
        screenshot("support-attachment-accepted")
    }

}
