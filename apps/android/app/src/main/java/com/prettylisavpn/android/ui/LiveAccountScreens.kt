package com.prettylisavpn.android.ui

import android.content.Intent
import androidx.core.net.toUri
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.Image
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
import androidx.navigation.compose.*
import com.prettylisavpn.android.BuildConfig
import com.prettylisavpn.android.data.*
import java.util.UUID

@Composable
internal fun LiveAccountScreens(model: ScreenModel, logout: () -> Unit) {
    val tr = strings()
    val state by model.state.collectAsState()
    val nav = rememberNavController()
    val entry by nav.currentBackStackEntryAsState()
    val route = entry?.destination?.route ?: "HOME"
    fun go(value: String) { model.clearError(); nav.navigate(value) { launchSingleTop = true } }
    Scaffold(containerColor = Brand.PurpleHeart, contentColor = Brand.Mercury,
        contentWindowInsets = WindowInsets(0,0,0,0),
        bottomBar = { if (route in setOf("HOME", "SETTINGS", "ABOUT")) PhoneNavigation(route) { dest ->
            nav.navigate(dest.name) { popUpTo("HOME"); launchSingleTop = true }
        } },
    ) { padding ->
        NavHost(nav, "HOME", Modifier.padding(padding).consumeWindowInsets(padding)) {
            composable("HOME") {
                LaunchedEffect(Unit) { model.load(Area.MESSAGES) }
                PhoneScreen("live-account") {
                    Image(painterResource(R.drawable.prettylisavpn_logo), "PrettyLisaVPN", contentScale = ContentScale.Fit, colorFilter = ColorFilter.tint(Brand.Mercury), modifier = Modifier.fillMaxWidth().height(96.dp).testTag("live-brand-logo"))
                    BrandCard {
                        Text(state.data.email, Modifier.testTag("account-email"))
                        Text(tr(R.string.ui_plan_0, state.data.plan))
                        Text(tr(R.string.ui_active_devices_0_5, state.data.activeDeviceCount))
                        Text(tr(R.string.ui_no_vpn_tunnel_is_running))
                        BrandActionButton(tr(R.string.ui_refresh_account), { model.load(Area.HOME) }, Modifier.testTag("account-refresh"), loading = state.loads[Area.HOME]?.phase == LoadPhase.LOADING)
                        OperationError(state.loads[Area.HOME]?.error); OperationError(state.error)
                        BrandActionButton(tr(R.string.ui_devices), { go("DEVICES") }, Modifier.testTag("live-devices"))
                        BrandActionButton(tr(R.string.ui_subscription), { go("SUBSCRIPTION") }, Modifier.testTag("live-subscription"))
                        BrandActionButton(tr(R.string.ui_messages_0, state.data.messages.size), { go("MESSAGES") }, Modifier.testTag("live-messages"))
                        BrandActionButton(tr(R.string.ui_contact_support), { go("SUPPORT") }, Modifier.testTag("live-support"))
                        BrandActionButton(tr(R.string.ui_sign_out), logout, Modifier.testTag("live-logout"), enabled = !state.busy)
                    }
                    BrandCard { BrandActionButton(tr(R.string.ui_connect_vpn_unavailable), {}, enabled = false) }
                }
            }
            composable("SETTINGS") { PhoneScreen("live-settings") {
                ScreenHeading(tr(R.string.ui_settings))
                BrandCard {
                    BrandActionButton(tr(R.string.ui_devices), { go("DEVICES") }, Modifier.testTag("settings-devices"))
                    BrandActionButton(tr(R.string.ui_subscription), { go("SUBSCRIPTION") }, Modifier.testTag("settings-subscription"))
                    BrandActionButton(tr(R.string.ui_sign_out), logout, enabled = !state.busy)
                }
            } }
            composable("ABOUT") { PhoneScreen("live-about") {
                ScreenHeading(tr(R.string.ui_about))
                BrandCard {
                    Text("PrettyLisaVPN"); Text("Android ${BuildConfig.VERSION_NAME}")
                    Text(tr(R.string.ui_build_0, BuildConfig.SOURCE_SHA.take(12)))
                    BrandActionButton(tr(R.string.ui_contact_support), { go("SUPPORT") })
                    BrandActionButton(tr(R.string.ui_account_messages), { go("MESSAGES") })
                }
            } }
            composable("DEVICES") { LiveDevices(model) { nav.popBackStack() } }
            composable("MESSAGES") { messageEntry ->
                LiveMessages(model, { nav.popBackStack() }) { destination ->
                    if (nav.currentBackStackEntry?.id == messageEntry.id) go(destination)
                }
            }
            composable("SUBSCRIPTION") { LiveSubscription(model) { nav.popBackStack() } }
            composable("SUPPORT") { support -> LiveSupport(model, support.savedStateHandle) { nav.popBackStack() } }
        }
    }
    BackHandler(enabled = route in setOf("SETTINGS", "ABOUT")) { nav.popBackStack("HOME", false) }
}

@Composable
private fun LiveLoad(model: ScreenModel, area: Area, content: @Composable () -> Unit) {
    val tr = strings()
    val state by model.state.collectAsState()
    LaunchedEffect(area) { model.load(area) }
    val load = state.loads[area] ?: Load()
    if (load.phase in setOf(LoadPhase.IDLE, LoadPhase.LOADING)) CircularProgressIndicator(color = Brand.Viking, modifier = Modifier.testTag("live-loading-${area.name}"))
    if (load.phase == LoadPhase.ERROR) BrandCard { OperationError(load.error) }
    if (state.data.refreshWarning != null) BrandCard { Text(tr.error(state.data.refreshWarning!!)) }
    // Existing data stays visible on failed refresh; mutations are guarded independently.
    if (load.phase !in setOf(LoadPhase.IDLE, LoadPhase.LOADING)) content()
    BrandActionButton(tr(R.string.ui_refresh), { model.load(area) }, Modifier.testTag("live-refresh-${area.name}"), enabled = load.phase != LoadPhase.LOADING && !state.busy)
}

@Composable
private fun LiveDevices(model: ScreenModel, back: () -> Unit) {
    val tr = strings()
    val state by model.state.collectAsState()
    var target by rememberSaveable { mutableStateOf<String?>(null) }
    PhoneScreen("live-devices-screen") {
        ScreenHeading(tr(R.string.ui_devices), back)
        LiveLoad(model, Area.DEVICES) {
            if (state.data.devices.isEmpty()) BrandCard { Text(tr(R.string.ui_no_devices_to_display)) }
            state.data.devices.forEach { device -> BrandCard {
                Text(device.name + if (device.current) tr(R.string.ui_this_device) else "")
                Text("id: ${device.id}")
                Text(tr(R.string.ui_added_0, device.added))
                Text(tr(R.string.ui_last_login_0, device.lastLogin ?: tr(R.string.ui_unavailable)))
                Text(if (device.active) tr(R.string.ui_active) else tr(R.string.ui_revoked))
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
private fun LiveMessages(model: ScreenModel, back: () -> Unit, navigate: (String) -> Unit) {
    val tr = strings()
    val state by model.state.collectAsState()
    PhoneScreen("live-messages-screen") {
        ScreenHeading(tr(R.string.ui_account_messages), back)
        LiveLoad(model, Area.MESSAGES) {
            if (state.data.messages.isEmpty()) BrandCard { Text(tr(R.string.ui_no_unread_messages)) }
            state.data.messages.forEach { message -> BrandCard {
                Text(message.title, style = MaterialTheme.typography.titleLarge); Text(message.body)
                Text(tr(R.string.ui_revision_0, message.revision), style = MaterialTheme.typography.bodySmall)
                message.destination?.let { dest -> BrandActionButton(message.actionLabel ?: tr(R.string.ui_view_details), {
                    model.perform(Command.Acknowledge(message.id, message.revision)) { navigate(dest) }
                }, Modifier.testTag("message-action-${message.id}"), enabled = !state.busy && state.loads[Area.MESSAGES]?.phase == LoadPhase.READY) }
                BrandActionButton(if (message.dismissLabel == "understood") tr(R.string.ui_understood) else message.dismissLabel, { model.perform(Command.Acknowledge(message.id, message.revision)) }, Modifier.testTag("live-ack-${message.id}"), enabled = state.loads[Area.MESSAGES]?.phase == LoadPhase.READY, loading = state.busy)
            } }
            OperationError(state.error)
            BrandActionButton(tr(R.string.ui_later), back, Modifier.testTag("messages-later"))
        }
    }
}

private fun money(amount: Long, currency: String) = "${currency} ${java.math.BigDecimal.valueOf(amount, 2).toPlainString()}"
@Composable
private fun LiveSubscription(model: ScreenModel, back: () -> Unit) {
    val tr = strings()
    val state by model.state.collectAsState()
    var currency by rememberSaveable { mutableStateOf("RUB") }
    var route by rememberSaveable { mutableStateOf("MIR") }
    var action by rememberSaveable { mutableStateOf<String?>(null) }
    var confirmedRevision by rememberSaveable { mutableStateOf("") }
    var requestId by rememberSaveable { mutableStateOf(UUID.randomUUID().toString()) }
    val context = LocalContext.current
    LaunchedEffect(state.data.billing?.revision, action) {
        if (action != null && confirmedRevision != state.data.billing?.revision) action = null
    }
    PhoneScreen("live-subscription-screen") {
        ScreenHeading(tr(R.string.ui_subscription), back)
        LiveLoad(model, Area.BILLING) {
            val billing = state.data.billing
            if (billing != null) BrandCard {
                Text("${billing.plan} · ${billing.status}", style = MaterialTheme.typography.titleLarge)
                Text(tr(R.string.ui_paid_until_0, billing.paidUntil ?: tr(R.string.ui_no_paid_period)), Modifier.testTag("live-paid-until"))
                Text(tr(R.string.ui_auto_renewal_0, if (billing.autoRenew) tr(R.string.ui_on) else tr(R.string.ui_off)))
                Text(tr(R.string.ui_payment_method_0, billing.method ?: tr(R.string.ui_none)))
                Text(tr(R.string.ui_current_price_0, billing.currentPrice ?: tr(R.string.ui_unavailable)))
                Text(tr(R.string.ui_provider_0, billing.mode), Modifier.testTag("provider-mode"))
                if (billing.mode != "LIVE" || !billing.available) Text(tr(R.string.ui_payment_actions_are_unavailable_no_payment_provider_will_be_opene))
                listOf("RUB", "USD").forEach { code -> BrandActionButton("${code}${if (code == currency) " ✓" else ""}", { currency = code; route = if (code == "RUB") "MIR" else "BANK_CARD" }, enabled = !state.busy && !state.data.paymentPending) }
                billing.offers.forEach { offer ->
                    offer.prices[currency]?.let { p -> Text(tr(R.string.ui_premium_month_0_1, money(p.amount, currency), p.original?.let { tr(R.string.ui_was_0, money(it, currency)) } ?: "")) }
                }
                billing.routes.forEach { cap ->
                    BrandActionButton(tr(R.string.ui_0_1_2_auto_renew_3, cap.label, if (route == cap.id) " ✓" else "", cap.currencies.joinToString(), cap.recurring.joinToString().ifEmpty { tr(R.string.ui_unavailable) }), { route = cap.id }, Modifier.testTag("live-route-${cap.id}"), enabled = currency in cap.currencies && !state.busy && !state.data.paymentPending)
                }
                billingActions.forEach { kind ->
                    val purchase = kind in setOf("SUBSCRIBE", "RENEW")
                    val allowedRoute = !purchase || (billing.offers.size == 1 && billing.routes.any { it.id == route && currency in it.currencies })
                    BrandActionButton(tr.action(kind), { model.clearError(); requestId = UUID.randomUUID().toString(); confirmedRevision = billing.revision; action = kind }, Modifier.testTag("live-pay-${kind}"), enabled = state.data.operationsReady && billing.permits(kind) && allowedRoute && !state.data.paymentPending && !state.data.stale && !state.busy && state.loads[Area.BILLING]?.phase == LoadPhase.READY)
                }
                if (state.data.paymentPending) {
                    Text(tr(R.string.ui_an_operation_needs_confirmation_refresh_its_status_before_startin))
                    BrandActionButton(tr(R.string.ui_check_operation), { model.perform(Command.ConfirmPayment) }, Modifier.testTag("live-check-payment"), loading = state.busy)
                    if (state.data.billingRetryAvailable) BrandActionButton(tr(R.string.ui_retry_original_operation), { model.perform(Command.Payment(requestId, "RENEW", route, currency)) }, Modifier.testTag("live-retry-payment"), enabled = billing.mode == "LIVE" && billing.available && !state.busy)
                }
                state.data.billingOperation?.let { operation ->
                    Text(tr(R.string.ui_operation_0_1, operation.id, operation.status))
                    val url = operation.redirect?.let { value -> runCatching { value.toUri().takeIf { it.scheme == "https" && it.host != null && it.userInfo == null && it.fragment == null && it.port in setOf(-1,443) } }.getOrNull() }
                    if (url != null && operation.status == "PENDING") BrandActionButton(tr(R.string.ui_continue_with_payment_provider), {
                        runCatching { context.startActivity(Intent(Intent.ACTION_VIEW, url)) }
                    }, enabled = billing.mode == "LIVE" && billing.available)
                }
                if (action == null) OperationError(state.error)
            }
        }
    }
    action?.let { kind -> ConfirmDialog(tr.action(kind) + "?", tr(R.string.ui_review_the_displayed_price_and_currency_cancel_change_method_pres), tr(R.string.ui_confirm), state, { action = null }) {
        model.perform(Command.Payment(requestId, kind, route, currency, confirmedRevision)) { action = null }
    } }
}

@Composable
private fun LiveSupport(model: ScreenModel, draft: SavedStateHandle, back: () -> Unit) {
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
    fun releaseImages() { selected.forEach { value -> runCatching { context.contentResolver.releasePersistableUriPermission(value.toUri(), Intent.FLAG_GRANT_READ_URI_PERMISSION) } } }
    LaunchedEffect(state.data.supportFrozen) { if (state.data.supportFrozen && selected.isNotEmpty()) { releaseImages(); draft["selected"] = arrayListOf<String>() } }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { values ->
        if (values.size + selected.size > 3) pickerError = R.string.ui_choose_at_most_3_images
        else draft["selected"] = ArrayList((selected + values.map { uri ->
            runCatching { context.contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION) }
            uri.toString()
        }).distinct())
    }
    val close = { if (!state.data.supportFrozen && (subject.isNotEmpty() || description.isNotEmpty() || selected.isNotEmpty())) discard = true else back() }
    BackHandler { close() }
    PhoneScreen("live-support-screen") {
        ScreenHeading(tr(R.string.ui_help_and_support), close)
        LaunchedEffect(Unit) { model.load(Area.SUPPORT) }
        BrandCard {
            if (state.data.supportFrozen) {
                Text(tr(R.string.ui_reference_0, state.data.supportReceipt), Modifier.testTag("live-support-receipt"))
                Text(tr(R.string.ui_status_0, state.data.supportStatus ?: tr(R.string.ui_not_yet_confirmed)))
                Text(if (state.data.supportStatus == "SENT") tr(R.string.ui_the_support_email_was_sent) else tr(R.string.ui_a_delivery_is_not_confirmed_until_the_server_reports_sent))
                BrandActionButton(tr(R.string.ui_check_status), { model.perform(Command.SupportStatus) }, Modifier.testTag("live-support-status"), loading = state.busy)
                if (state.data.supportAwaiting) BrandActionButton(tr(R.string.ui_retry_original_request), { model.perform(Command.Support(id, subject, description, email, 0)) }, Modifier.testTag("live-support-retry"), loading = state.busy)
                if (state.data.supportStatus in setOf("SENT", "FAILED", "EXPIRED")) BrandActionButton(tr(R.string.ui_new_request), {
                    model.perform(Command.NewSupport) { draft["subject"] = ""; draft["description"] = ""; draft["selected"] = arrayListOf<String>(); draft["request-id"] = UUID.randomUUID().toString() }
                })
            } else {
                Text(tr(R.string.ui_send_a_message_to_prettylisavpn_support_only_your_text_reply_addr))
                BrandTextField(subject, { draft["subject"] = it.take(120) }, tr(R.string.ui_subject), Modifier.testTag("live-support-subject"), enabled = !state.busy)
                BrandTextField(description, { draft["description"] = it.take(4000) }, tr(R.string.ui_description), Modifier.testTag("live-support-description"), singleLine = false, minLines = 3, enabled = !state.busy)
                BrandTextField(email, { draft["email"] = it.take(254) }, tr(R.string.ui_reply_email), Modifier.testTag("live-support-email"), enabled = !state.busy)
                Text(tr(R.string.ui_selected_images_0_3_png_jpeg_webp_5_mb_each_10_mb_total, selected.size))
                BrandActionButton(tr(R.string.ui_attach_screenshots), { picker.launch(arrayOf("image/png", "image/jpeg", "image/webp")) }, Modifier.testTag("live-support-attach"), enabled = selected.size < 3 && !state.busy)
                if (selected.isNotEmpty()) BrandActionButton(tr(R.string.ui_remove_selected_images), { releaseImages(); draft["selected"] = arrayListOf<String>() }, enabled = !state.busy)
                Text(tr(R.string.ui_technical_diagnostics_are_unavailable_for_android))
                OperationError(pickerError?.let { tr(it) })
                BrandActionButton(tr(R.string.ui_send_to_support), { model.perform(Command.Support(id, subject.trim(), description.trim(), email.trim(), selected.size, selected.toList())) }, Modifier.testTag("live-support-send"), enabled = state.data.operationsReady && subject.isNotBlank() && description.isNotBlank() && android.util.Patterns.EMAIL_ADDRESS.matcher(email.trim()).matches(), loading = state.busy)
            }
            OperationError(state.error)
            OperationError(state.loads[Area.SUPPORT]?.error)
            if (!state.data.operationsReady) BrandActionButton(tr(R.string.ui_retry_secure_operation_recovery), { model.load(Area.SUPPORT) }, Modifier.testTag("live-recover-journal"), enabled = !state.busy)
            BrandActionButton(tr(R.string.ui_done), close)
        }
    }
    if (discard) ConfirmDialog(tr(R.string.ui_discard_draft), tr(R.string.ui_this_removes_the_local_draft_sending_or_accepted_requests_are_not), tr(R.string.ui_discard), state, { discard = false }) { releaseImages(); discard = false; back() }
}
