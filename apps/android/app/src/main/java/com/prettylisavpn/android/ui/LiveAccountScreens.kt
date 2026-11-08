package com.prettylisavpn.android.ui

import android.content.Intent
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Close
import androidx.core.net.toUri
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.Image
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.layout.ContentScale
import com.prettylisavpn.android.R
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.navigation.compose.*
import com.prettylisavpn.android.data.*
import java.util.UUID

@Composable
internal fun LiveAccountScreens(model: ScreenModel, messageBlocked: Boolean = false, logout: () -> Unit) {
    val tr = strings()
    val context = LocalContext.current
    val methodSelection = remember { com.prettylisavpn.android.vpn.DeviceMethodSelection.get(context) }
    val state by model.state.collectAsState()
    val nav = rememberNavController()
    val entry by nav.currentBackStackEntryAsState()
    val route = entry?.destination?.route ?: "HOME"
    val demo = state.data.plan.equals("Demo", ignoreCase = true)
    fun register() { model.perform(Command.Logout) { model.emailDraft = "" } }
    fun registerToBuy() { model.perform(Command.Logout) { model.emailDraft = ""; model.afterLoginSubscription = true } }
    LaunchedEffect(Unit) { if (model.afterLoginSubscription) { model.afterLoginSubscription = false; nav.navigate("SUBSCRIPTION") } }
    fun go(value: String) {
        if (demo && value == "SUPPORT") { register(); return }
        model.clearError(); nav.navigate(value) { launchSingleTop = true }
    }
    Scaffold(containerColor = Brand.PurpleHeart, contentColor = Brand.Mercury,
        contentWindowInsets = WindowInsets(0,0,0,0),
        bottomBar = { if (route in setOf("HOME", "SETTINGS", "ABOUT")) PhoneNavigation(route) { dest ->
            nav.navigate(dest.name) { popUpTo("HOME"); launchSingleTop = true }
        } },
    ) { padding ->
        NavHost(nav, "HOME", Modifier.padding(padding).consumeWindowInsets(padding)) {
            composable("HOME") { LiveHome(model, register = ::register) { go("SUBSCRIPTION") } }
            composable("SETTINGS") { PhoneScreen("live-settings") {
                ScreenHeading(tr(R.string.ui_settings))
                SettingsOption(tr(R.string.ui_subscription), tr(R.string.ui_manage_your_plan_and_payments), R.drawable.nav_subscription, "settings-subscription") { go("SUBSCRIPTION") }
                SettingsOption(tr(R.string.ui_devices), tr(R.string.ui_manage_account_access), R.drawable.nav_devices, "settings-devices") { go("DEVICES") }
                SettingsOption(tr(R.string.advanced_settings), tr(R.string.connection_methods), R.drawable.nav_settings, "settings-advanced") { go("ADVANCED") }
                SettingsOption(tr(R.string.ui_sign_out), tr(R.string.dash_end_session), R.drawable.nav_logout, "settings-logout", danger = true, enabled = !state.busy) { logout() }
                OperationError(state.error)
            } }
            composable("ABOUT") { AboutScreen("live-about", { go("SUPPORT") }, navigate = { go(it) }) }
            composable("ADVANCED") { AdvancedSettings(methodSelection) { nav.popBackStack() } }
            composable("DEVICES") { LiveDevices(model) { nav.popBackStack() } }
            composable("SUBSCRIPTION") { LiveSubscription(model, ::register, ::registerToBuy) { nav.popBackStack() } }
            composable("SUPPORT") { support -> LiveSupport(model, support.savedStateHandle) { nav.popBackStack() } }
        }
    }
    if (!demo) AccountMessagePopup(model, messageBlocked) { go(it) }
    BackHandler(enabled = route in setOf("SETTINGS", "ABOUT")) { nav.popBackStack("HOME", false) }
}

@Composable
private fun LiveLoad(model: ScreenModel, area: Area, content: @Composable () -> Unit) {
    val tr = strings()
    val state by model.state.collectAsState()
    LaunchedEffect(area) { model.load(area) }
    val load = state.loads[area] ?: Load()
    if (area !in setOf(Area.DEVICES, Area.BILLING) && load.phase in setOf(LoadPhase.IDLE, LoadPhase.LOADING)) CircularProgressIndicator(color = Brand.Viking, modifier = Modifier.testTag("live-loading-${area.name}"))
    if (load.phase == LoadPhase.ERROR) BrandCard { OperationError(load.error) }
    if (state.data.refreshWarning != null) BrandCard { Text(tr.error(state.data.refreshWarning!!)) }
    // Existing data stays visible on failed refresh; mutations are guarded independently.
    if (load.phase !in setOf(LoadPhase.IDLE, LoadPhase.LOADING) || (area == Area.DEVICES && state.data.devices.isNotEmpty()) || (area == Area.BILLING && state.data.billing != null)) content()
    if (area !in setOf(Area.DEVICES, Area.BILLING)) BrandActionButton(tr(R.string.ui_refresh), { model.load(area) }, Modifier.testTag("live-refresh-${area.name}"), enabled = load.phase != LoadPhase.LOADING && !state.busy)
}

@Composable
private fun LiveDevices(model: ScreenModel, back: () -> Unit) {
    val tr = strings()
    val state by model.state.collectAsState()
    var target by rememberSaveable { mutableStateOf<String?>(null) }
    val language by LocalPresentation.current.preference.language.collectAsState()
    val locale = java.util.Locale.forLanguageTag(language.code)
    PhoneScreen("live-devices-screen", onRefresh = { model.load(Area.DEVICES) }, refreshing = state.loads[Area.DEVICES]?.phase == LoadPhase.LOADING) {
        ScreenHeading(tr(R.string.ui_devices), back)
        LiveLoad(model, Area.DEVICES) {
            val devices = state.data.devices.filter { it.active }.sortedByDescending { it.current }
            if (devices.isEmpty()) BrandCard { Text(tr(R.string.ui_no_devices_to_display)) }
            devices.forEach { device -> BrandCard(Modifier.testTag("device-${device.id}")) {
                Text(device.name, style = MaterialTheme.typography.titleMedium)
                if (device.current) Surface(color = Brand.Heliotrope, contentColor = Brand.Christalle, shape = MaterialTheme.shapes.small) {
                    Text(tr(R.string.ui_current_device), Modifier.padding(horizontal = 12.dp, vertical = 6.dp).testTag("current-device-badge"), style = MaterialTheme.typography.titleMedium)
                }
                Text(if (device.active) tr(R.string.ui_active) else tr(R.string.ui_revoked), style = MaterialTheme.typography.labelMedium, color = Brand.Scorpion)
                Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Text("id", style = MaterialTheme.typography.bodySmall, color = Brand.Scorpion)
                    Text(device.id, style = MaterialTheme.typography.bodySmall.copy(fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace))
                }
                DetailValue(tr(R.string.dash_added), readableDate(device.added, locale, java.time.ZoneId.systemDefault()) ?: tr(R.string.unavailable))
                DetailValue(tr(R.string.dash_last_login), readableDate(device.lastLogin, locale, java.time.ZoneId.systemDefault()) ?: tr(R.string.ui_no_data))
                BrandActionButton(tr(R.string.ui_revoke_access_26), { model.clearError(); target = device.id }, Modifier.testTag("live-revoke-${device.id}"), enabled = device.active && !state.busy && state.loads[Area.DEVICES]?.phase == LoadPhase.READY)
            } }
            if (target == null) OperationError(state.error)
        }
    }
    target?.let { id -> ConfirmDialog(tr(R.string.ui_revoke_access), tr(R.string.ui_this_device_will_lose_account_access_revoking_this_device_ends_it), tr(R.string.ui_revoke), state, { target = null }) {
        model.perform(Command.Revoke(id)) { target = null }
    } }
}

@Composable
private fun LiveSubscription(model: ScreenModel, register: () -> Unit, registerToBuy: () -> Unit, back: () -> Unit) {
    val tr = strings()
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    DisposableEffect(lifecycle, model) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) model.load(Area.BILLING)
        }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer) }
    }
    val state by model.state.collectAsState()
    var currency by rememberSaveable { mutableStateOf("RUB") }
    var route by rememberSaveable { mutableStateOf("MIR") }
    var action by rememberSaveable { mutableStateOf<String?>(null) }
    var confirmedRevision by rememberSaveable { mutableStateOf("") }
    var requestId by rememberSaveable { mutableStateOf(UUID.randomUUID().toString()) }
    val context = LocalContext.current
    val language by LocalPresentation.current.preference.language.collectAsState()
    val locale = java.util.Locale.forLanguageTag(language.code)
    val billing = state.data.billing
    val currentPlan = billing?.plan ?: state.data.plan.uppercase(java.util.Locale.ROOT)
    val demo = currentPlan == "DEMO"
    var purchaseUnavailable by rememberSaveable { mutableStateOf(false) }
    val contract = subscriptionContractPrice(billing?.currentPrice)?.takeIf { billing?.plan == "PREMIUM" && !billing.newContractRequired }
    val purchaseRoutes = billing?.let { subscriptionPurchaseRoutes(it, currency) }.orEmpty()
    LaunchedEffect(billing?.revision, currency) {
        val currencies = billing?.offers?.flatMap { it.prices.keys }.orEmpty()
        if (contract != null && currency != contract.first) currency = contract.first
        else if (contract == null && currencies.isNotEmpty() && currency !in currencies) currency = currencies.first()
        if (purchaseRoutes.none { it.id == route }) route = purchaseRoutes.firstOrNull()?.id.orEmpty()
    }
    var now by remember { mutableStateOf(java.time.Instant.now()) }
    LaunchedEffect(Unit) { while (true) { now = java.time.Instant.now(); kotlinx.coroutines.delay(60_000) } }
    LaunchedEffect(state.data.billing?.revision, action) {
        if (action != null && confirmedRevision != state.data.billing?.revision) action = null
    }
    fun buy() {
        if (demo) { registerToBuy(); return }
        val kind = listOf("SUBSCRIBE", "RENEW").firstOrNull { billing?.permits(it) == true }
        if (kind != null && state.data.operationsReady && billing?.offers?.size == 1 &&
            purchaseRoutes.any { it.id == route } && !state.data.stale && state.loads[Area.BILLING]?.phase == LoadPhase.READY) {
            model.clearError(); requestId = UUID.randomUUID().toString(); confirmedRevision = billing!!.revision; action = kind
        } else purchaseUnavailable = true
    }
    PhoneScreen("live-subscription-screen", onRefresh = { if (!state.busy) model.load(Area.BILLING) },
        refreshing = state.loads[Area.BILLING]?.phase == LoadPhase.LOADING, refreshAtEnd = false) {
        ScreenHeading(tr(R.string.ui_subscription), back)
        LiveLoad(model, Area.BILLING) {
            Text(tr(R.string.ui_your_plan) + " · " + planLabel(currentPlan),
                Modifier.testTag("billing-current-plan"), style = MaterialTheme.typography.labelLarge)
            val offer = billing?.offers?.firstOrNull()
            val showOffer = currentPlan != "PREMIUM" || billing?.newContractRequired == true
            val prices = if (showOffer) offer?.prices ?: referenceOffers().first().prices else contract?.let { mapOf(it) }.orEmpty()
            SubscriptionPriceCard(planLabel("PREMIUM"), prices, contract?.first ?: currency, locale,
                if (showOffer) { value -> currency = value } else null, !state.busy && !state.data.paymentPending,
                Modifier.testTag(if (billing == null && showOffer) "billing-reference-prices" else if (showOffer) "billing-offer" else "billing-contract-price"),
                note = if (!showOffer) (if (contract != null) tr(R.string.billing_fixed_price) else tr(R.string.subscription_price_unconfirmed))
                    else if (billing == null) tr(R.string.billing_reference_prices) else if (currentPlan == "PREMIUM") tr(R.string.billing_resubscribe) else null,
                featured = true, current = currentPlan == "PREMIUM") {
                    if (showOffer) {
                        if (purchaseRoutes.isNotEmpty()) Column {
                            purchaseRoutes.forEach { cap ->
                                FilterChip(selected = route == cap.id, onClick = { route = cap.id }, label = { Text(cap.label) },
                                    colors = FilterChipDefaults.filterChipColors(labelColor = Brand.Mercury, selectedLabelColor = Brand.Christalle, selectedContainerColor = Brand.Viking),
                                    modifier = Modifier.heightIn(min = 48.dp).testTag("live-route-${cap.id}"), enabled = !state.busy && !state.data.paymentPending)
                            }
                        }
                        BrandActionButton(tr(R.string.plan_buy), ::buy, Modifier.testTag("plan-buy"), enabled = !state.busy && !state.data.paymentPending)
                    }
                }
            if (currentPlan != "PREMIUM") {
                PlanTierCard("FREE", currentPlan == "FREE", if (demo) register else null, !state.busy)
                PlanTierCard("DEMO", demo)
            }
            if (billing != null) {
                if (billing.paidUntil != null) BrandCard(Modifier.testTag("billing-access")) {
                    Text(planLabel(billing.plan), style = MaterialTheme.typography.titleLarge)
                    if (billing.plan == "PLATINUM") Text(tr(R.string.subscription_platinum), style = MaterialTheme.typography.bodyMedium, color = Brand.Scorpion)
                    val paid = billing.paidUntil
                    SubscriptionDetail(tr(R.string.subscription_active_until), readableDate(paid, locale, java.time.ZoneId.systemDefault()) ?: paid, "live-paid-until")
                    if (billing.status in setOf("ACTIVE", "CANCELED")) remainingPaidDays(paid, now)?.let {
                        Text(tr(R.string.billing_days_left, it), Modifier.testTag("billing-days-left"), color = Brand.Christalle, style = MaterialTheme.typography.labelLarge)
                    }
                }
                if (billing.plan == "PREMIUM" || billing.method != null || billing.autoRenew) BrandCard(Modifier.testTag("billing-payment-details")) {
                    Text(tr(R.string.subscription_payment_details), style = MaterialTheme.typography.titleLarge)
                    SubscriptionDetail(tr(R.string.subscription_auto_renew), tr(if (billing.autoRenew) R.string.ui_on else R.string.ui_off))
                    SubscriptionDetail(tr(R.string.subscription_payment_method), if (billing.methodKind == "SBP") tr(R.string.billing_sbp_account) else billing.method ?: tr(R.string.ui_none))
                    billing.nextChargeAt?.let { next ->
                        HorizontalDivider(color = Brand.Christalle.copy(alpha = 0.12f))
                        SubscriptionDetail(tr(R.string.subscription_next_charge), readableDate(next, locale, java.time.ZoneId.systemDefault()) ?: next, "billing-next-charge")
                        Text(billing.nextChargePrice?.let { subscriptionContractPrice(it) }?.let { subscriptionMoney(it.second.amount, it.first, locale) } ?: billing.nextChargePrice.orEmpty(), style = MaterialTheme.typography.headlineSmall, color = Brand.Christalle)
                    }
                }
                Spacer(Modifier.testTag("provider-mode"))
                if (state.data.paymentPending) BrandCard {
                    Text(tr(R.string.ui_an_operation_needs_confirmation_refresh_its_status_before_startin))
                    BrandActionButton(tr(R.string.ui_check_operation), { model.perform(Command.ConfirmPayment) }, Modifier.testTag("live-check-payment"), loading = state.busy)
                    if (state.data.billingRetryAvailable) BrandActionButton(tr(R.string.ui_retry_original_operation), { model.perform(Command.Payment(requestId, "RENEW", route, currency)) }, Modifier.testTag("live-retry-payment"), enabled = billing.mode == "LIVE" && billing.available && !state.busy)
                }
                state.data.billingOperation?.let { operation -> BrandCard {
                    Text(tr(R.string.ui_operation_0_1, operation.id, operation.status))
                    val url = operation.redirect?.let { value -> runCatching { value.toUri().takeIf { it.scheme == "https" && it.host != null && it.userInfo == null && it.fragment == null && it.port in setOf(-1,443) } }.getOrNull() }
                    if (url != null && operation.status == "PENDING") BrandActionButton(tr(R.string.ui_continue_with_payment_provider), {
                        runCatching { context.startActivity(Intent(Intent.ACTION_VIEW, url)) }
                    }, enabled = billing.mode == "LIVE" && billing.available)
                } }
                if (billing.plan == "PREMIUM" || billing.method != null || billing.autoRenew) BrandCard(Modifier.testTag("billing-management")) {
                    if (action == null) OperationError(state.error)
                    SubscriptionManageButton(tr(R.string.subscription_change), { model.openBillingPortal { url -> context.startActivity(Intent(Intent.ACTION_VIEW, url.toUri())) } }, "billing-portal", !state.busy && !model.fixture && !state.data.paymentPending)
                    listOf("CHANGE_METHOD", "CANCEL").filter { billing.permits(it) }.forEach { kind ->
                        if (kind == "CANCEL") Text(tr(R.string.billing_cancel_detail), style = MaterialTheme.typography.bodySmall, color = Brand.Scorpion)
                        SubscriptionManageButton(tr(if (kind == "CANCEL") R.string.subscription_delete else R.string.billing_replace_card),
                            { model.clearError(); requestId = UUID.randomUUID().toString(); confirmedRevision = billing.revision; action = kind }, "live-pay-$kind",
                            state.data.operationsReady && !state.data.paymentPending && !state.data.stale && !state.busy && state.loads[Area.BILLING]?.phase == LoadPhase.READY,
                            danger = kind == "CANCEL")
                    }
                }
            }
        }
    }
    if (purchaseUnavailable) AlertDialog(onDismissRequest = { purchaseUnavailable = false },
        modifier = Modifier.testTag("purchase-unavailable"), containerColor = Brand.Mercury,
        title = { Text(tr(R.string.subscription_premium_offer)) },
        text = { Text(tr(R.string.subscription_payments_unavailable)) },
        confirmButton = { TextButton({ purchaseUnavailable = false }) { Text(tr(R.string.ui_understood)) } })
    action?.let { kind ->
        if (kind == "CANCEL") ConfirmDialog(
            tr.action(kind) + "?", tr(R.string.billing_cancel_detail), tr(R.string.ui_confirm), state,
            { if (!state.busy) action = null },
            extraContent = {
                if (state.data.billing?.permits("CHANGE_METHOD") == true) {
                    Text(tr(R.string.billing_replace_prompt))
                    BrandActionButton(tr(R.string.billing_replace_card), { action = "CHANGE_METHOD"; requestId = UUID.randomUUID().toString() }, enabled = !state.busy)
                }
            },
        ) {
            model.perform(Command.Payment(requestId, kind, route, currency, confirmedRevision)) { action = null }
        } else ConfirmDialog(tr.action(kind) + "?", tr(R.string.ui_review_the_displayed_price_and_currency_cancel_change_method_pres), tr(R.string.ui_confirm), state, { action = null }) {
            model.perform(Command.Payment(requestId, kind, route, currency, confirmedRevision)) { action = null }
        }
    }
}

@Composable
internal fun LiveSupport(model: ScreenModel, draft: SavedStateHandle, back: () -> Unit) {
    val tr = strings()
    val state by model.state.collectAsState()
    val subject by draft.getStateFlow("subject", "").collectAsState()
    val description by draft.getStateFlow("description", "").collectAsState()
    val email by draft.getStateFlow("email", state.data.email).collectAsState()
    val selected by draft.getStateFlow("selected", arrayListOf<String>()).collectAsState()
    val id by draft.getStateFlow("request-id", UUID.randomUUID().toString()).collectAsState()
    LaunchedEffect(id) { draft["request-id"] = id }
    var discard by rememberSaveable { mutableStateOf(false) }
    var pickerError by remember { mutableStateOf<Int?>(null) }
    val context = LocalContext.current
    val transfer by model.supportTransfer.collectAsState(SupportTransfer())
    var infos by remember { mutableStateOf<Map<String, SupportImageInfo>>(emptyMap()) }
    var failed by remember { mutableStateOf<Set<String>>(emptySet()) }
    var validating by remember { mutableStateOf(false) }
    val includeDiagnostics by draft.getStateFlow("diagnostics", true).collectAsState()
    var showDiagnostics by rememberSaveable { mutableStateOf(false) }
    val presentation = LocalPresentation.current
    val language by presentation.preference.language.collectAsState()
    val version by presentation.version.collectAsState()
    val vpnStatus = model.vpn?.status?.collectAsState()?.value
    var diagnostics by remember { mutableStateOf<com.google.gson.JsonObject?>(null) }
    LaunchedEffect(version, language, state.data.plan, vpnStatus, includeDiagnostics) {
        diagnostics = null
        if (includeDiagnostics) diagnostics = kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
            androidDiagnostics(context, version, language.code, state.data.plan, vpnStatus)
        }
    }
    LaunchedEffect(selected) {
        validating = true
        failed = emptySet()
        infos = infos.filterKeys { it in selected }
        for (value in selected) {
            try { infos = infos + (value to supportImageInfo(context, value)) }
            catch (e: kotlinx.coroutines.CancellationException) { throw e }
            catch (_: Exception) { failed = failed + value }
        }
        validating = false
    }
    fun releaseImages() { selected.forEach { value -> runCatching { context.contentResolver.releasePersistableUriPermission(value.toUri(), Intent.FLAG_GRANT_READ_URI_PERMISSION) } } }

    LaunchedEffect(state.data.supportFrozen) {
        if (state.data.supportFrozen && selected.isNotEmpty()) {
            draft["attachment-names"] = ArrayList(selected.mapNotNull { infos[it]?.name })
            releaseImages()
            draft["selected"] = arrayListOf<String>()
        }
    }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { values ->
        val combined = (selected + values.map { it.toString() }).distinct()
        if (combined.size > 3) pickerError = R.string.ui_choose_at_most_3_images
        else {
            pickerError = null
            values.forEach { uri -> runCatching { context.contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION) } }
            draft["selected"] = ArrayList(combined)
        }
    }
    val close = { if (state.busy) Unit else if (!state.data.supportFrozen && (subject.isNotEmpty() || description.isNotEmpty() || email != state.data.email || selected.isNotEmpty())) discard = true else back() }
    BackHandler { close() }
    PhoneScreen("live-support-screen") {
        ScreenHeading(tr(R.string.ui_help_and_support), close)
        LaunchedEffect(Unit) { model.load(Area.SUPPORT) }
        BrandCard {
            if (state.data.supportFrozen) {
                draft.get<ArrayList<String>>("attachment-names")?.forEach { Text(it, style = MaterialTheme.typography.bodySmall) }
                Text(tr(R.string.ui_reference_0, state.data.supportReceipt), Modifier.testTag("live-support-receipt"))
                Text(tr(R.string.ui_status_0, state.data.supportStatus ?: tr(R.string.ui_not_yet_confirmed)))
                Text(if (state.data.supportStatus == "SENT") tr(R.string.ui_the_support_email_was_sent) else tr(R.string.ui_a_delivery_is_not_confirmed_until_the_server_reports_sent))
                BrandActionButton(tr(R.string.ui_check_status), { model.perform(Command.SupportStatus) }, Modifier.testTag("live-support-status"), loading = state.busy)
                if (state.data.supportAwaiting) BrandActionButton(tr(R.string.ui_retry_original_request), { model.perform(Command.Support(id, subject, description, email, 0)) }, Modifier.testTag("live-support-retry"), loading = state.busy)
                if (state.data.supportStatus in setOf("SENT", "FAILED", "EXPIRED")) BrandActionButton(tr(R.string.ui_new_request), {
                    model.perform(Command.NewSupport) { releaseImages(); draft["attachment-names"] = arrayListOf<String>(); draft["subject"] = ""; draft["description"] = ""; draft["selected"] = arrayListOf<String>(); draft["request-id"] = UUID.randomUUID().toString() }
                })
            } else {
                Text(tr(R.string.ui_send_a_message_to_prettylisavpn_support_only_your_text_reply_addr))
                BrandTextField(subject, { draft["subject"] = it.take(120) }, tr(R.string.ui_subject), Modifier.testTag("live-support-subject"), enabled = !state.busy)
                BrandTextField(description, { draft["description"] = it.take(4000) }, tr(R.string.ui_description), Modifier.testTag("live-support-description"), singleLine = false, minLines = 3, enabled = !state.busy)
                BrandTextField(email, { draft["email"] = it.take(254) }, tr(R.string.ui_reply_email), Modifier.testTag("live-support-email"), enabled = !state.busy)
                Text(tr(R.string.ui_selected_images_0_3_png_jpeg_webp_5_mb_each_10_mb_total, selected.size))
                BrandActionButton(tr(R.string.ui_attach_screenshots), { picker.launch(arrayOf("image/png", "image/jpeg", "image/webp")) }, Modifier.testTag("live-support-attach"), enabled = selected.size < 3 && !state.busy)
                selected.forEachIndexed { index, value ->
                    Row(Modifier.fillMaxWidth().testTag("support-image-$index"), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text(infos[value]?.name ?: tr(R.string.dash_reading_image), style = MaterialTheme.typography.bodyMedium)
                            Text(when {
                                value in failed -> tr(R.string.dash_image_error)
                                transfer.phase == "UPLOADING" -> tr(R.string.dash_upload_progress, (transfer.fraction * 100).toInt())
                                value in infos -> tr(R.string.dash_image_ready, ((infos[value]!!.size + 1023) / 1024).toInt())
                                else -> tr(R.string.dash_reading_image)
                            }, style = MaterialTheme.typography.bodySmall, color = if (value in failed) Brand.PersianRed else Brand.Scorpion)
                            if (value !in infos && value !in failed) LinearProgressIndicator(Modifier.fillMaxWidth(), color = Brand.PurpleHeart)
                        }
                        IconButton({
                            runCatching { context.contentResolver.releasePersistableUriPermission(value.toUri(), Intent.FLAG_GRANT_READ_URI_PERMISSION) }
                            draft["selected"] = ArrayList(selected.filterNot { it == value })
                        }, Modifier.testTag("support-remove-$index"), enabled = !state.busy) {
                            Icon(androidx.compose.material.icons.Icons.Outlined.Close, tr(R.string.dash_remove_image))
                        }
                    }
                }
                if (infos.values.sumOf { it.size } > 10 * 1024 * 1024) Text(tr(R.string.detail_0), color = Brand.PersianRed)
                Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                    Checkbox(includeDiagnostics, { draft["diagnostics"] = it }, Modifier.testTag("support-diagnostics"), enabled = !state.busy)
                    Text(tr(R.string.dash_diagnostics), Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
                }
                Text(tr(R.string.support_local_logs), style = MaterialTheme.typography.bodySmall)
                if (includeDiagnostics) {
                    TextButton({ showDiagnostics = !showDiagnostics }, Modifier.testTag("support-diagnostics-toggle")) { Text(tr(R.string.dash_diagnostics_preview)) }
                    if (showDiagnostics) Box(Modifier.fillMaxWidth().heightIn(max = 280.dp).verticalScroll(rememberScrollState())) {
                        SelectionContainer {
                            Text(diagnostics?.let { com.google.gson.GsonBuilder().setPrettyPrinting().create().toJson(it) } ?: tr(R.string.processing), style = MaterialTheme.typography.bodySmall, modifier = Modifier.testTag("support-diagnostics-preview"))
                        }
                    }
                }
                if (state.busy) {
                    Text(if (transfer.phase == "UPLOADING") tr(R.string.dash_upload_progress, (transfer.fraction * 100).toInt()) else tr(R.string.processing), style = MaterialTheme.typography.bodySmall)
                    if (transfer.phase == "UPLOADING") LinearProgressIndicator(progress = { transfer.fraction }, modifier = Modifier.fillMaxWidth(), color = Brand.PurpleHeart)
                }
                OperationError(pickerError?.let { tr(it) })
                BrandActionButton(tr(R.string.ui_send_to_support), { model.perform(Command.Support(id, subject.trim(), description.trim(), email.trim(), selected.size, selected.toList(), if (includeDiagnostics) diagnostics?.deepCopy() else null)) }, Modifier.testTag("live-support-send"), enabled = state.data.operationsReady && (!includeDiagnostics || diagnostics != null) && !validating && failed.isEmpty() && infos.size == selected.size && infos.values.sumOf { it.size } <= 10 * 1024 * 1024 && subject.isNotBlank() && description.isNotBlank() && android.util.Patterns.EMAIL_ADDRESS.matcher(email.trim()).matches(), loading = state.busy)
            }
            OperationError(state.error)
            OperationError(state.loads[Area.SUPPORT]?.error)
            if (!state.data.operationsReady) BrandActionButton(tr(R.string.ui_retry_secure_operation_recovery), { model.load(Area.SUPPORT) }, Modifier.testTag("live-recover-journal"), enabled = !state.busy)
        }
    }
    if (discard) ConfirmDialog(tr(R.string.ui_discard_draft), tr(R.string.ui_this_removes_the_local_draft_sending_or_accepted_requests_are_not), tr(R.string.ui_discard), state, { discard = false }) { releaseImages(); discard = false; back() }
}
