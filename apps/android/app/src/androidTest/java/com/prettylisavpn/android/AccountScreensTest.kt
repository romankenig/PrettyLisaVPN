package com.prettylisavpn.android

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.prettylisavpn.android.auth.*
import com.prettylisavpn.android.data.*
import java.io.File
import androidx.activity.compose.setContent
import org.junit.*
import org.junit.Assert.*
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class AccountScreensTest {
    @get:Rule val compose=createAndroidComposeRule<MainActivity>()
    private val owner="30000000-0000-0000-0000-000000000001"
    private val device="30000000-0000-0000-0000-000000000002"
    private val current="30000000-0000-0000-0000-000000000004"
    private val message="30000000-0000-0000-0000-000000000003"
    private var mode="DISABLED"
    private var revision="r1"
    private var active=true
    private var ackFail=false
    private var messages=false
    private var messageExpiry:String?=null
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
        override suspend fun trafficServices(token:String) = listOf(
            com.prettylisavpn.android.vpn.TrafficService("0bd811da-f080-4f25-887a-67bf534ac2c6", "youtube", "YouTube", "youtube", listOf("youtube.com", "*.youtube.com")),
            com.prettylisavpn.android.vpn.TrafficService("4e2b8d7c-289f-4c57-8f26-aeb680408cda", "instagram", "Instagram", "instagram", listOf("instagram.com", "*.instagram.com")))
        override suspend fun devices(token:String): List<Device> { deviceReads++; return listOf(Device(device,"Other phone",false,"2026-10-20T00:00:00Z",null,active), Device(current,"Current phone",true,"2026-10-21T00:00:00Z",null)) }
        override suspend fun revoke(token:String,id:String):Device { active=false;return devices(token).first() }
        override suspend fun locations(token:String)=LocationOptions(countries(token),80)
        override suspend fun countries(token:String)=listOf(Country("DE","DE","80",true),Country("FR","FR","60",true))
        override suspend fun messages(token:String)=if(messages)listOf(AccountMessage(message,2,"Account notice","Synthetic test message","SUBSCRIPTION",expiresAt=messageExpiry))else emptyList()
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
        com.prettylisavpn.android.vpn.DeviceTrafficSelection.get(InstrumentationRegistry.getInstrumentation().targetContext).save(com.prettylisavpn.android.vpn.TrafficSelection())
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
    @After fun reset() { SourceFactory.sourceForTests=null; com.prettylisavpn.android.vpn.DeviceTrafficSelection.get(InstrumentationRegistry.getInstrumentation().targetContext).save(com.prettylisavpn.android.vpn.TrafficSelection()) }
    private fun waitFor(tag:String)=compose.waitUntil(10_000) { compose.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty() }
    private fun click(tag:String) {
        if(compose.onAllNodes(hasTestTag(tag) and hasAnyAncestor(hasScrollAction())).fetchSemanticsNodes().isNotEmpty()) compose.onNodeWithTag(tag).performScrollTo()
        compose.waitForIdle();InstrumentationRegistry.getInstrumentation().uiAutomation.waitForIdle(300,5000)
        compose.onNodeWithTag(tag).performClick()
    }
    private fun idle()=compose.waitUntil(10_000) { !model.state.value.busy }
    private fun screenshot(name:String) {
        compose.runOnUiThread { compose.activity.window.decorView.invalidate() }
        compose.waitForIdle();val i=InstrumentationRegistry.getInstrumentation();i.uiAutomation.waitForIdle(500,5000)
        val dir=File(i.targetContext.getExternalFilesDir(null),"acceptance/account-api");check(dir.mkdirs()||dir.isDirectory)
        val file=File(dir,"$name.png")
        android.os.ParcelFileDescriptor.AutoCloseInputStream(i.uiAutomation.executeShellCommand("screencap -p")).use { input -> file.outputStream().use { input.copyTo(it) } }
        val header=ByteArray(8)
        java.io.DataInputStream(file.inputStream()).use { it.readFully(header) }
        check(header.contentEquals(byteArrayOf(0x89.toByte(),0x50,0x4e,0x47,0x0d,0x0a,0x1a,0x0a)))
    }
    @Test fun devicesRevokeUpdatesHomeAndBack() {
        click("tab_SETTINGS");screenshot("settings-windows");click("settings-devices");waitFor("live-revoke-$device")
        compose.onNodeWithTag("live-refresh-DEVICES").assertDoesNotExist()
        compose.onNodeWithText("2026-10-20T00:00:00Z", substring=true).assertDoesNotExist()
        val reads=deviceReads
        compose.onNodeWithTag("live-devices-screen").performTouchInput { swipeDown() }
        compose.waitUntil(10_000) { deviceReads>reads && model.state.value.loads[Area.DEVICES]?.phase==LoadPhase.READY }
        compose.onNodeWithTag("live-revoke-$device").performScrollTo()
        val afterDown=deviceReads
        compose.onNodeWithTag("live-devices-screen").performTouchInput { swipeUp() }
        compose.waitUntil(10_000) { deviceReads>afterDown && model.state.value.loads[Area.DEVICES]?.phase==LoadPhase.READY }
        val badge=compose.onNodeWithTag("current-device-badge").fetchSemanticsNode().boundsInRoot
        val other=compose.onNodeWithTag("device-$device").fetchSemanticsNode().boundsInRoot
        assertTrue("current device must be first",badge.top < other.top)
        compose.onNodeWithTag("device-$current").performScrollTo()
        screenshot("devices-current-first")
        click("live-revoke-$device")
        click("confirm-dialog");idle()
        compose.onNodeWithTag("device-$device").assertDoesNotExist();compose.onNodeWithTag("current-device-badge").assertExists();screenshot("devices-revoked")
        compose.runOnUiThread { compose.activity.onBackPressedDispatcher.onBackPressed() };waitFor("live-settings")
        click("tab_HOME");compose.onNodeWithText("1 / 5").assertExists()
    }

    @Test fun secondLocationAppearsOnlyInSplitModes() {
        compose.onNodeWithTag("vpn-location").assertDoesNotExist()
        val store = com.prettylisavpn.android.vpn.DeviceTrafficSelection.get(InstrumentationRegistry.getInstrumentation().targetContext)
        for (mode in listOf("include", "exclude")) {
            compose.runOnUiThread { store.save(store.current().copy(mode = mode)) }
            waitFor("vpn-location")
            compose.onNodeWithTag("vpn-location").performScrollTo()
            screenshot("vpn-location-$mode")
            compose.onNodeWithTag("home-network").assertExists()
        }
        compose.runOnUiThread { store.save(store.current().copy(mode = "all")) }
        compose.onNodeWithTag("vpn-location").assertDoesNotExist()
        compose.onNodeWithTag("home-network").assertExists()
    }

    @Test fun trafficListsAreIndependentAndPersistAfterRecreation() {
        click("traffic-services"); waitFor("traffic-service-youtube")
        click("traffic-service-youtube")
        compose.onNodeWithTag("traffic-service-youtube").assertIsOn()
        screenshot("traffic-include")
        click("traffic-tab-exclude")
        compose.onNodeWithTag("traffic-service-youtube").assertIsOff()
        click("traffic-service-instagram")
        screenshot("traffic-exclude")
        click("traffic-save")
        compose.waitUntil(10_000) { compose.onAllNodesWithTag("traffic-dialog").fetchSemanticsNodes().isEmpty() }
        compose.activityRule.scenario.recreate(); waitFor("live-account")
        click("traffic-services"); waitFor("traffic-service-youtube")
        compose.onNodeWithTag("traffic-service-youtube").assertIsOn()
        click("traffic-tab-exclude")
        compose.onNodeWithTag("traffic-service-instagram").assertIsOn()
    }
    @Test fun messagesPopupOnlyNavigatesAfterSuccessfulAck() {
        messages=true;ackFail=true
        compose.runOnUiThread { model.load(Area.MESSAGES) };waitFor("account-message-popup")
        screenshot("message-popup")
        click("message-action-$message");idle()
        compose.onNodeWithTag("account-message-popup").assertExists();assertTrue(messages)
        compose.onNodeWithTag("provider-mode").assertDoesNotExist()
        ackFail=false;click("message-action-$message");waitFor("provider-mode");assertFalse(messages)
        compose.onNodeWithTag("account-message-popup").assertDoesNotExist()
    }
    @Test fun messageLaterDoesNotAckOrCreateAnInboxAndSurvivesRotation() {
        click("tab_SETTINGS");compose.onNodeWithTag("settings-messages").assertDoesNotExist()
        messages=true;compose.runOnUiThread { model.load(Area.MESSAGES) };waitFor("account-message-popup")
        click("messages-later");assertTrue(messages)
        compose.onNodeWithTag("account-message-popup").assertDoesNotExist()
        compose.activityRule.scenario.recreate();waitFor("live-settings")
        compose.onNodeWithTag("account-message-popup").assertDoesNotExist()
        click("tab_SETTINGS");compose.onNodeWithTag("settings-messages").assertDoesNotExist()
        screenshot("settings-without-inbox")
    }
    @Test fun popupWaitsForAnotherConfirmationDialog() {
        click("tab_SETTINGS");click("settings-logout");waitFor("confirmation-dialog")
        messages=true;compose.runOnUiThread { model.load(Area.MESSAGES) };idle()
        compose.onNodeWithTag("account-message-popup").assertDoesNotExist()
        click("dismiss-dialog");waitFor("account-message-popup");click("messages-later")
        assertTrue(model.state.value.data.signedIn)
    }
    @Test fun expiredPopupDoesNotReturnFromBackground() {
        messages=true;messageExpiry=java.time.Instant.now().plusSeconds(3).toString()
        compose.runOnUiThread { model.load(Area.MESSAGES) };waitFor("account-message-popup")
        compose.activityRule.scenario.moveToState(androidx.lifecycle.Lifecycle.State.CREATED)
        Thread.sleep(3_500)
        compose.activityRule.scenario.moveToState(androidx.lifecycle.Lifecycle.State.RESUMED)
        waitFor("live-account")
        compose.onNodeWithTag("account-message-popup").assertDoesNotExist()
        assertTrue("expiry must not send ACK",messages)
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
    @Test fun homeMatchesWindowsAndMissingVpnPortCannotConnect() {
        compose.onNodeWithTag("account-email").assertTextEquals("screens@example.com")
        for(tag in listOf("live-devices","live-subscription","live-messages","live-support","account-refresh","live-logout")) compose.onNodeWithTag(tag).assertDoesNotExist()
        screenshot("home-account-summary")
        compose.onNodeWithTag("home-connect").performScrollTo().assertIsNotEnabled()
        assertFalse(model.state.value.data.simulatedConnection)
        assertEquals(0,starts)
        compose.onNodeWithTag("home-manual").assertDoesNotExist()
        click("home-country")
        compose.onNodeWithTag("home-country-AUTO").assertExists()
        compose.onNodeWithTag("home-top-DE").assertExists()
        compose.onAllNodesWithContentDescription("availability 80 out of 100").assertAny(hasText("80"))
        screenshot("home-location-dropdown")
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
                        androidx.compose.material3.Surface(color=com.prettylisavpn.android.ui.Brand.PurpleHeart,contentColor=com.prettylisavpn.android.ui.Brand.Mercury) {
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
