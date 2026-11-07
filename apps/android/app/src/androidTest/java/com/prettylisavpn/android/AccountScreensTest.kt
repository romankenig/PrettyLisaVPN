package com.prettylisavpn.android

import androidx.compose.ui.test.*
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.text.TextLayoutResult
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
    private var plan="Premium"
    private var revision="r1"
    private var active=true
    private var billingFail=false
    private var ackFail=false
    private var messages=false
    private var messageExpiry:String?=null
    private var starts=0
    private var billingReads=0
    private var offerRub=39900L
    private var lastIntent:BillingIntent?=null
    private var sends=0
    private var deviceReads=0
    private var profileReads=0
    private var countryReads=0
    private var uploadGate:kotlinx.coroutines.CompletableDeferred<Unit>?=null
    private var submitted:SupportSubmission?=null
    private var receipt:SupportReceipt?=null
    private lateinit var model:ScreenModel
    private val api=object:AuthApi {
        override suspend fun demo(deviceKey:String):Tokens { plan="Demo";return tokens() }
        override suspend fun requestOtp(email:String)=Unit
        override suspend fun verifyOtp(email:String,code:String,installationId:String,deviceName:String)=tokens()
        fun tokens()=Tokens("fake",900,Credentials(device,"fake","2030-01-01T00:00:00Z"))
        override suspend fun refresh(credentials:Credentials)=tokens()
        override suspend fun me(access:String):Profile { profileReads++; return Profile(if(plan=="Demo")"" else "screens@example.com",plan,if(plan=="Demo")1 else if(active)2 else 1,owner,
            if(plan in setOf("Free","Demo")) FreeTime(if(plan=="Demo")900 else 3600,0,"2030-01-01T00:00:00Z",System.currentTimeMillis(),if(plan=="Demo")900 else 3600) else null) }
        override suspend fun logout(access:String)=Unit
    }
    private val accounts=object:AccountApi {
        override suspend fun trafficServices(token:String) = listOf(
            com.prettylisavpn.android.vpn.TrafficService("0bd811da-f080-4f25-887a-67bf534ac2c6", "youtube", "YouTube", "youtube", listOf("youtube.com", "*.youtube.com")),
            com.prettylisavpn.android.vpn.TrafficService("4e2b8d7c-289f-4c57-8f26-aeb680408cda", "instagram", "Instagram", "instagram", listOf("instagram.com", "*.instagram.com")))
        override suspend fun devices(token:String): List<Device> { deviceReads++; return (if(plan=="Demo")emptyList() else listOf(Device(device,"Other phone",false,"2026-10-20T00:00:00Z",null,active))) + listOf(Device(current,"Current phone",true,"2026-10-21T00:00:00Z",null)) }
        override suspend fun revoke(token:String,id:String):Device { active=false;return devices(token).first() }
        override suspend fun locations(token:String):LocationOptions { countryReads++; return LocationOptions(countries(token),80) }
        override suspend fun countries(token:String)=listOf(Country("DE","DE","80",true),Country("FR","FR","60",true))
        override suspend fun messages(token:String)=if(messages)listOf(AccountMessage(message,2,"Account notice","Synthetic test message","SUBSCRIPTION",expiresAt=messageExpiry))else emptyList()
        override suspend fun acknowledge(token:String,id:String,revision:Int) { if(ackFail)throw AuthFailure("offline");messages=false }
        override suspend fun overview(token:String): BillingOverview {
            billingReads++
            if(billingFail)throw AuthFailure("BILLING_UNAVAILABLE")
            val premium=plan=="Premium"
            return BillingOverview(revision,mode,true,plan.uppercase(java.util.Locale.ROOT),"ACTIVE","2030-01-01T00:00:00Z",premium,if(premium)"Test card" else null,if(premium)"RUB 100.00" else null,
                routeIds.map { PaymentRoute(it,it,if(mode=="LIVE"&&it=="MIR")setOf("RUB")else emptySet(),emptySet()) },
                listOf(AccountOffer("30000000-0000-0000-0000-000000000005",mapOf("RUB" to OfferPrice(offerRub,49900),"USD" to OfferPrice(500,700)))),
                if(premium)billingActions else setOf("SUBSCRIBE"),null,newContractRequired=!premium)
        }
        override suspend fun start(token:String,intent:BillingIntent):OperationReceipt { starts++;lastIntent=intent;return OperationReceipt(device,"PENDING") }
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
        SourceFactory.sourceForTests=LiveSessionSource(SessionCoordinator(api,vault,"Test",demoIdentity={ "a".repeat(64) }),accounts,uploads={ readSupportImages(instrumentation.targetContext,it) })
        compose.runOnUiThread { compose.activity.viewModelStore.clear() };compose.activityRule.scenario.recreate()
        compose.runOnUiThread { model=compose.activity.screenModel };waitFor("live-account")
    }
    @After fun reset() {
        SourceFactory.sourceForTests=null
        val context=InstrumentationRegistry.getInstrumentation().targetContext
        context.getSharedPreferences("presentation",android.content.Context.MODE_PRIVATE).edit().putString("language","en").commit()
        com.prettylisavpn.android.vpn.DeviceTrafficSelection.get(context).save(com.prettylisavpn.android.vpn.TrafficSelection())
    }
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
    @Test fun planBadgesAndFreeUpgradeFollowTheCurrentAccount() {
        compose.waitUntil(10_000) { model.state.value.loads[Area.HOME]?.phase == LoadPhase.READY }
        compose.onNodeWithText("PREMIUM ⭐").assertExists()
        compose.onNodeWithTag("home-upgrade").assertDoesNotExist()
        screenshot("home-premium-plan")
        compose.runOnUiThread { plan="Free"; model.load(Area.HOME) }
        waitFor("home-upgrade")
        compose.onNodeWithText("FREE 🕊️").assertExists()
        screenshot("home-free-upgrade")
        click("home-upgrade"); waitFor("provider-mode")
        compose.onNodeWithTag("live-subscription-screen").assertExists()
        compose.onNodeWithTag("live-pay-SUBSCRIBE").assertDoesNotExist()
        assertEquals(0, starts)
        screenshot("home-upgrade-subscription")
        compose.runOnUiThread { compose.activity.onBackPressedDispatcher.onBackPressed() }
        waitFor("live-account")
        compose.runOnUiThread { plan="Platinum"; model.load(Area.HOME) }
        compose.waitUntil(10_000) { model.state.value.data.plan == "Platinum" }
        compose.onNodeWithText("PLATINUM 💎").assertExists()
        compose.onNodeWithTag("home-upgrade").assertDoesNotExist()
        screenshot("home-platinum-plan")
    }

    @Test fun documentsAreReadableInAboutAndQuietBelowSignIn() {
        click("tab_ABOUT");compose.onNodeWithTag("about-documents").performScrollTo();screenshot("about-documents")
        for(key in listOf("terms","privacy","refunds","payments")) compose.onNodeWithTag("about-document-$key").assertExists()
        compose.runOnUiThread { model.perform(Command.Logout) };waitFor("screen_LOGIN")
        compose.onNodeWithTag("auth-submit").assertExists()
        compose.onNodeWithTag("auth-documents").performScrollTo();screenshot("auth-documents-demo")
        for(key in listOf("terms","privacy","refunds","payments")) compose.onNodeWithTag("auth-document-$key").assertExists()
        click("auth-demo");waitFor("demo-traffic")
        compose.onNodeWithText("DEMO ⏳").assertExists()
        compose.onNodeWithText("15:00").assertExists()
        screenshot("demo-home")
    }

    @Test fun demoLocksLeadToRegistrationAndFreeHasItsFullHour() {
        compose.runOnUiThread { plan="Demo";model.load(Area.HOME) };waitFor("demo-traffic")
        compose.onNodeWithTag("demo-traffic").performScrollTo();screenshot("demo-locked-traffic")
        compose.onNodeWithTag("demo-locked-include").assertExists()
        compose.onNodeWithTag("demo-locked-exclude").assertExists()
        click("tab_SETTINGS");screenshot("demo-settings")
        compose.onNodeWithTag("demo-locked-methods").assertDoesNotExist()
        click("settings-devices");waitFor("current-device-badge");screenshot("demo-devices")
        compose.onNodeWithTag("device-$device").assertDoesNotExist()
        compose.runOnUiThread { compose.activity.onBackPressedDispatcher.onBackPressed() };waitFor("live-settings")
        click("settings-advanced");waitFor("advanced-settings");screenshot("demo-advanced")
        click("method-wireguard");compose.onNodeWithTag("method-wireguard").assertIsOff()
        click("all-methods");compose.onNodeWithTag("method-wireguard").assertIsOn()
        compose.runOnUiThread { compose.activity.onBackPressedDispatcher.onBackPressed() };waitFor("live-settings")
        click("tab_HOME");click("home-country");screenshot("demo-countries")
        click("home-country-DE");waitFor("screen_LOGIN")
        assertEquals(0,billingReads)
        compose.onNodeWithTag("login-email").performTextInput("registered@example.com");click("auth-submit");waitFor("screen_OTP")
        compose.onNodeWithTag("otp").performTextInput("123456")
        compose.runOnUiThread { plan="Free" };click("auth-submit");waitFor("live-account")
        compose.onNodeWithText("FREE 🕊️").assertExists()
        compose.onNodeWithText("60:00").assertExists()
        compose.onNodeWithTag("demo-traffic").assertDoesNotExist()
        screenshot("demo-upgraded-free")
    }

    @Test fun guestComparisonAndBuyReturnToSubscriptionAfterRegistration() {
        click("language-picker");click("language-ru")
        compose.runOnUiThread { model.perform(Command.Logout) };waitFor("screen_LOGIN")
        compose.onNodeWithText("15 минут в день на этом устройстве.",substring=true).assertDoesNotExist()
        compose.onNodeWithTag("auth-documents").performScrollTo();screenshot("plan-polish-login-ru")
        click("auth-demo");waitFor("demo-traffic")
        compose.onNodeWithTag("vpn-reset-methods").assertDoesNotExist()
        screenshot("plan-polish-demo-home-ru")
        click("home-upgrade");waitFor("plan-buy")
        compose.onNodeWithTag("live-subscription-screen").assertExists()
        compose.onNodeWithTag("billing-price").assertTextEquals("399 ₽")
        compose.onNodeWithTag("billing-offer").performScrollTo();screenshot("plan-polish-demo-premium-ru")
        compose.onNodeWithTag("plan-tier-FREE").performScrollTo();screenshot("plan-polish-demo-free-ru")
        compose.onNodeWithTag("current-plan-DEMO").performScrollTo();screenshot("plan-polish-demo-current-ru")
        assertEquals(0,billingReads)
        click("plan-buy");waitFor("screen_LOGIN")
        compose.onNodeWithTag("login-email").performTextInput("buyer@example.com");click("auth-submit");waitFor("screen_OTP")
        compose.onNodeWithTag("otp").performTextInput("123456")
        compose.runOnUiThread { plan="Free" };click("auth-submit");waitFor("plan-buy")
        compose.onNodeWithTag("current-plan-FREE").assertExists()
        compose.onNodeWithTag("billing-offer").performScrollTo();screenshot("plan-polish-free-premium-ru")
        compose.onNodeWithTag("plan-tier-FREE").performScrollTo();screenshot("plan-polish-free-current-ru")
        click("plan-buy");waitFor("purchase-unavailable")
        assertEquals(0,starts)
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

    @Test fun homePullDownRefreshesAccountAndCountriesWithoutNavigation() {
        waitFor("live-account")
        compose.waitUntil(10_000) { model.state.value.loads[Area.HOME]?.phase==LoadPhase.READY && model.state.value.loads[Area.COUNTRIES]?.phase==LoadPhase.READY }
        val profiles = profileReads
        val countries = countryReads
        compose.onNodeWithTag("live-account").performTouchInput { swipeDown() }
        compose.waitUntil(10_000) { profileReads>profiles && countryReads>countries }
        compose.onNodeWithTag("live-account").assertExists()
        compose.onNodeWithTag("account-summary").assertExists()
        screenshot("home-refreshed")
    }

    @Test fun splitSelectionWithoutConnectedMetadataHasNoSecondLocation() {
        compose.onNodeWithTag("vpn-location").assertDoesNotExist()
        val store = com.prettylisavpn.android.vpn.DeviceTrafficSelection.get(InstrumentationRegistry.getInstrumentation().targetContext)
        val list = com.prettylisavpn.android.vpn.TrafficList(
            services = kotlinx.coroutines.runBlocking { accounts.trafficServices("fake") },
            masks = (0..31).map { "site$it.example.com" })
        compose.onNodeWithTag("traffic-services").assertDoesNotExist()
        compose.onNodeWithTag("traffic-selected-strip").assertDoesNotExist()
        compose.runOnUiThread { store.save(store.current().copy(include = list, exclude = list)) }
        for (mode in listOf("include", "exclude")) {
            click("traffic-mode-menu"); click("traffic-mode-$mode")
            compose.onNodeWithTag("traffic-services").assertExists()
            compose.onNodeWithTag("traffic-mode-description").assertDoesNotExist()
            compose.onNodeWithTag("vpn-location").assertDoesNotExist()
            compose.onNodeWithTag("vpn-location-divider").assertDoesNotExist()
            compose.onNodeWithTag("traffic-services").performScrollTo()
            compose.onNodeWithTag("traffic-selected-more").assertIsDisplayed()
            val custom = compose.onNodeWithContentDescription("site0.example.com")
            custom.assertIsDisplayed()
            val original = compose.onNodeWithContentDescription("YouTube")
            assertTrue(original.fetchSemanticsNode().boundsInRoot.left < custom.fetchSemanticsNode().boundsInRoot.left)
            val strip = compose.onNodeWithTag("traffic-selected-strip").fetchSemanticsNode().boundsInRoot
            val picker = compose.onNodeWithTag("traffic-services").fetchSemanticsNode().boundsInRoot
            assertTrue(strip.bottom <= picker.top)
            assertEquals(32, store.current().include.masks.size)
            assertEquals(32, store.current().exclude.masks.size)
            screenshot("split-selection-$mode")
            compose.onNodeWithTag("home-network").assertExists()
        }
        click("traffic-mode-menu"); click("traffic-mode-all")
        compose.onNodeWithTag("traffic-services").assertDoesNotExist()
        compose.onNodeWithTag("traffic-selected-strip").assertDoesNotExist()
        compose.onNodeWithTag("vpn-location").assertDoesNotExist()
        compose.onNodeWithTag("home-network").assertExists()
    }

    @Test fun secondaryLocationHidesMissingMetadataAndRecoversWithoutInventingRegion() {
        val location=androidx.compose.runtime.mutableStateOf<com.prettylisavpn.android.ui.PublicLocation?>(null)
        val connected=androidx.compose.runtime.mutableStateOf(true)
        val mode=androidx.compose.runtime.mutableStateOf("include")
        compose.runOnUiThread {
            compose.activity.setContent {
                com.prettylisavpn.android.ui.PrettyLisaTheme {
                    com.prettylisavpn.android.ui.LocalizedApp {
                        com.prettylisavpn.android.ui.PhoneScreen("secondary-location-test") {
                            com.prettylisavpn.android.ui.BrandCard {
                                androidx.compose.material3.Text("Protected traffic")
                                com.prettylisavpn.android.ui.SecondaryLocation(mode.value,connected.value,location.value,false)
                            }
                        }
                    }
                }
            }
        }
        waitFor("secondary-location-test")
        compose.onNodeWithTag("vpn-location").assertDoesNotExist()
        compose.onNodeWithTag("vpn-location-divider").assertDoesNotExist()
        screenshot("vpn-location-hidden")
        compose.runOnUiThread { location.value=com.prettylisavpn.android.ui.PublicLocation("198.51.100.42",null,null) }
        compose.onNodeWithText("IP: 198.51.100.42").assertIsDisplayed()
        compose.onNodeWithText("unavailable").assertDoesNotExist()
        screenshot("vpn-location-ip-only")
        compose.runOnUiThread { location.value=com.prettylisavpn.android.ui.PublicLocation("198.51.100.42","DE","Berlin") }
        compose.onNodeWithText("Berlin, Germany",substring=true).assertIsDisplayed()
        screenshot("vpn-location-observed")
        compose.runOnUiThread { connected.value=false }
        compose.onNodeWithTag("vpn-location").assertDoesNotExist()
        compose.runOnUiThread { connected.value=true;mode.value="all" }
        compose.onNodeWithTag("vpn-location").assertDoesNotExist()
        compose.runOnUiThread { mode.value="exclude" }
        compose.onNodeWithText("location without VPN:").assertIsDisplayed()
        compose.runOnUiThread { location.value=null }
        compose.onNodeWithTag("vpn-location").assertDoesNotExist()
        compose.onNodeWithTag("vpn-location-divider").assertDoesNotExist()
    }

    @Test fun trafficListsAreIndependentAndPersistAfterRecreation() {
        click("traffic-mode-menu"); click("traffic-mode-include")
        click("traffic-services"); waitFor("traffic-service-youtube")
        click("traffic-service-youtube")
        compose.onNodeWithTag("traffic-service-youtube").assertIsOn()
        screenshot("traffic-include")
        compose.onNodeWithTag("traffic-tab-exclude").assertDoesNotExist()
        click("traffic-save")
        compose.waitUntil(10_000) { compose.onAllNodesWithTag("traffic-dialog").fetchSemanticsNodes().isEmpty() }
        click("traffic-mode-menu"); click("traffic-mode-exclude")
        click("traffic-services"); waitFor("traffic-service-youtube")
        compose.onNodeWithTag("traffic-service-youtube").assertIsOff()
        click("traffic-service-instagram")
        screenshot("traffic-exclude")
        click("traffic-save")
        compose.waitUntil(10_000) { compose.onAllNodesWithTag("traffic-dialog").fetchSemanticsNodes().isEmpty() }
        compose.activityRule.scenario.recreate(); waitFor("live-account")
        click("traffic-services"); waitFor("traffic-service-youtube")
        compose.onNodeWithTag("traffic-service-instagram").assertIsOn()
        compose.onNodeWithTag("traffic-service-youtube").assertIsOff()
        click("traffic-save")
        compose.waitUntil(10_000) { compose.onAllNodesWithTag("traffic-dialog").fetchSemanticsNodes().isEmpty() }
        click("traffic-mode-menu"); click("traffic-mode-include")
        click("traffic-services"); waitFor("traffic-service-youtube")
        compose.onNodeWithTag("traffic-service-youtube").assertIsOn()
        compose.onNodeWithTag("traffic-service-instagram").assertIsOff()
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
    @Test fun unavailableBillingShowsReferencePricesWithoutPaymentActions() {
        compose.runOnUiThread { plan="Free";model.load(Area.HOME) };waitFor("home-upgrade")
        billingFail=true
        click("tab_SETTINGS");click("settings-subscription");waitFor("billing-reference-prices")
        compose.onNodeWithTag("billing-price").assertTextEquals("399 ₽")
        click("billing-currency-USD")
        compose.onNodeWithTag("billing-price").assertTextEquals("${'$'}5")
        for(kind in billingActions)compose.onNodeWithTag("live-pay-$kind").assertDoesNotExist()
        assertEquals(0,starts);screenshot("billing-reference-prices")
    }
    @Test fun disabledAndSandboxActionsAreHiddenAndPullRefreshes() {
        click("tab_SETTINGS");click("settings-subscription");waitFor("provider-mode")
        for(kind in billingActions)compose.onNodeWithTag("live-pay-$kind").assertDoesNotExist()
        for(route in routeIds)compose.onNodeWithTag("live-route-$route").assertDoesNotExist()
        compose.onNodeWithTag("live-refresh-BILLING").assertDoesNotExist()
        val reads=billingReads
        mode="SANDBOX"
        compose.onNodeWithTag("live-subscription-screen").performTouchInput { swipeDown(startY=height*0.25f,endY=height*0.9f,durationMillis=700) }
        compose.waitUntil(10_000) { billingReads>reads && model.state.value.data.billing?.mode=="SANDBOX" }
        for(kind in billingActions)compose.onNodeWithTag("live-pay-$kind").assertDoesNotExist()
        assertEquals(0,starts);screenshot("sandbox-read-only")
    }
    @Test fun platinumShowsReadableOfferCurrencyAndNoFakeContract() {
        plan="Platinum"
        click("tab_SETTINGS");click("settings-subscription");waitFor("billing-offer")
        click("language-picker");click("language-ru")
        compose.onNodeWithTag("billing-contract-price").assertDoesNotExist()
        compose.onNodeWithTag("billing-payment-details").assertDoesNotExist()
        compose.onNodeWithTag("live-pay-CANCEL").assertDoesNotExist()
        compose.onNodeWithTag("billing-price").assertTextEquals("399 ₽")
        compose.onNodeWithTag("billing-original-price").assertTextEquals("499 ₽")
        compose.onNodeWithTag("billing-offer").performScrollTo();screenshot("subscription-platinum-rub")
        click("billing-currency-USD")
        compose.onNodeWithTag("billing-price").assertTextEquals("${'$'}5")
        compose.onNodeWithTag("billing-original-price").assertTextEquals("${'$'}7")
        screenshot("subscription-platinum-usd")
        compose.onNodeWithTag("billing-management").assertDoesNotExist()
        click("plan-buy");waitFor("purchase-unavailable");screenshot("subscription-payment-unavailable")
        compose.runOnUiThread { compose.activity.onBackPressedDispatcher.onBackPressed() }
        assertEquals(0,starts)
        click("language-picker");click("language-en")
    }
    @Test fun subscriptionPriceRemainsReadableAtDoubleFontScale() {
        compose.runOnUiThread {
            compose.activity.setContent {
                com.prettylisavpn.android.ui.PrettyLisaTheme {
                    com.prettylisavpn.android.ui.LocalizedApp {
                        val density=androidx.compose.ui.platform.LocalDensity.current
                        androidx.compose.runtime.CompositionLocalProvider(androidx.compose.ui.platform.LocalDensity provides androidx.compose.ui.unit.Density(density.density,2f)) {
                            androidx.compose.material3.Surface(color=com.prettylisavpn.android.ui.Brand.PurpleHeart) {
                                com.prettylisavpn.android.ui.PhoneScreen("subscription-large-text") {
                                    com.prettylisavpn.android.ui.SubscriptionPriceCard("PREMIUM ⭐",mapOf("RUB" to OfferPrice(39900,49900),"USD" to OfferPrice(500,700)),
                                        "RUB",java.util.Locale.forLanguageTag("ru"),{},true,featured=true)
                                }
                            }
                        }
                    }
                }
            }
        }
        waitFor("billing-price")
        screenshot("subscription-large-text")
        val layouts=mutableListOf<TextLayoutResult>()
        compose.onNodeWithTag("billing-price").performSemanticsAction(SemanticsActions.GetTextLayoutResult) { it(layouts) }
        assertTrue(layouts.isNotEmpty())
        layouts.forEach { assertFalse("Price overflows: width=${it.didOverflowWidth}, height=${it.didOverflowHeight}, size=${it.size}",it.hasVisualOverflow) }
        compose.onNodeWithTag("billing-currency-RUB").assertIsSelected()
        compose.onNodeWithTag("billing-currency-USD").performScrollTo().assertIsDisplayed()
    }
    @Test fun agreedPriceAndCancellationKeepPaidAccessUntilConfirmation() {
        mode="LIVE";click("tab_SETTINGS");click("settings-subscription");waitFor("billing-contract-price")
        compose.onNodeWithTag("billing-price").assertTextEquals("100 ₽")
        compose.onNodeWithTag("billing-currency-USD").assertDoesNotExist()
        compose.onNodeWithTag("billing-offer").assertDoesNotExist()
        for(route in routeIds-setOf("MIR"))compose.onNodeWithTag("live-route-$route").assertDoesNotExist()
        compose.onNodeWithTag("billing-contract-price").performScrollTo();screenshot("subscription-contract-price")
        val paid=model.state.value.data.billing?.paidUntil
        click("live-pay-CANCEL");waitFor("confirmation-dialog")
        assertEquals(0,starts);screenshot("subscription-cancel-confirmation")
        click("confirm-dialog");idle()
        assertEquals(1,starts);assertEquals("CANCEL",lastIntent?.action)
        assertEquals(paid,model.state.value.data.billing?.paidUntil)
    }
    @Test fun freeBuyRequiresConfirmationAndUsesTheServerOffer() {
        mode="LIVE";plan="Free"
        click("tab_SETTINGS");click("settings-subscription");waitFor("plan-buy")
        click("plan-buy");waitFor("confirmation-dialog")
        assertEquals(0,starts)
        click("confirm-dialog");idle()
        assertEquals(1,starts);assertEquals("SUBSCRIBE",lastIntent?.action)
        assertEquals("RUB",lastIntent?.currency)
        assertEquals("30000000-0000-0000-0000-000000000005",lastIntent?.offer_id)
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
        compose.onNodeWithTag("about-faq-title").assertTextEquals("FAQ")
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
    @Test fun faqSelectionRevealsAnswerAndNavigatesToSubscription() {
        click("tab_ABOUT"); waitFor("live-about")
        click("faq-select"); click("faq-option-1")
        compose.onNodeWithTag("faq-answer").assertTextEquals(compose.activity.getString(R.string.faq_free_a))
        screenshot("about-faq-free")
        compose.onNodeWithTag("faq-link").assertDoesNotExist()
        click("faq-select"); click("faq-option-4")
        val split = compose.activity.getString(R.string.faq_split_a)
            .replace("[", "").replace("]", "")
        compose.onNodeWithTag("faq-answer").assertTextEquals(split)
        screenshot("about-faq-split")
        click("faq-select"); click("faq-option-2")
        val answer = compose.onNodeWithTag("faq-answer").performScrollTo()
        val layouts = mutableListOf<TextLayoutResult>()
        answer.performSemanticsAction(SemanticsActions.GetTextLayoutResult) { it(layouts) }
        val source = compose.activity.getString(R.string.faq_manage_a)
        val linkStart = source.indexOf('[')
        val linkEnd = source.indexOf(']') - 1
        val linkCenter = layouts.single().getBoundingBox((linkStart + linkEnd) / 2).center
        answer.performTouchInput { click(linkCenter) }
        waitFor("provider-mode")
        assertEquals(0, starts)
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
