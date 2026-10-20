package com.prettylisavpn.android.ui

import android.content.Intent
import androidx.core.net.toUri
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
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
                    ScreenHeading("PrettyLisaVPN")
                    BrandCard {
                        Text(state.data.email, Modifier.testTag("account-email"))
                        Text("Plan: ${state.data.plan}")
                        Text("Active devices: ${state.data.activeDeviceCount} / 5")
                        Text("No VPN tunnel is running.")
                        BrandActionButton("refresh account", { model.load(Area.HOME) }, Modifier.testTag("account-refresh"), loading = state.loads[Area.HOME]?.phase == LoadPhase.LOADING)
                        OperationError(state.loads[Area.HOME]?.error); OperationError(state.error)
                        BrandActionButton("devices", { go("DEVICES") }, Modifier.testTag("live-devices"))
                        BrandActionButton("subscription", { go("SUBSCRIPTION") }, Modifier.testTag("live-subscription"))
                        BrandActionButton("messages (${state.data.messages.size})", { go("MESSAGES") }, Modifier.testTag("live-messages"))
                        BrandActionButton("contact support", { go("SUPPORT") }, Modifier.testTag("live-support"))
                        BrandActionButton("sign out", logout, Modifier.testTag("live-logout"), enabled = !state.busy)
                    }
                    BrandCard { BrandActionButton("connect VPN · unavailable", {}, enabled = false) }
                }
            }
            composable("SETTINGS") { PhoneScreen("live-settings") {
                ScreenHeading("settings")
                BrandCard {
                    BrandActionButton("devices", { go("DEVICES") }, Modifier.testTag("settings-devices"))
                    BrandActionButton("subscription", { go("SUBSCRIPTION") }, Modifier.testTag("settings-subscription"))
                    BrandActionButton("sign out", logout, enabled = !state.busy)
                }
            } }
            composable("ABOUT") { PhoneScreen("live-about") {
                ScreenHeading("about")
                BrandCard {
                    Text("PrettyLisaVPN"); Text("Android ${BuildConfig.VERSION_NAME}")
                    Text("build: ${BuildConfig.SOURCE_SHA.take(12)}")
                    BrandActionButton("contact support", { go("SUPPORT") })
                    BrandActionButton("account messages", { go("MESSAGES") })
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
    val state by model.state.collectAsState()
    LaunchedEffect(area) { model.load(area) }
    val load = state.loads[area] ?: Load()
    if (load.phase in setOf(LoadPhase.IDLE, LoadPhase.LOADING)) CircularProgressIndicator(color = Brand.Viking, modifier = Modifier.testTag("live-loading-${area.name}"))
    if (load.phase == LoadPhase.ERROR) BrandCard { OperationError(load.error) }
    if (state.data.refreshWarning != null) BrandCard { Text(state.data.refreshWarning!!) }
    // Existing data stays visible on failed refresh; mutations are guarded independently.
    if (load.phase !in setOf(LoadPhase.IDLE, LoadPhase.LOADING)) content()
    BrandActionButton("refresh", { model.load(area) }, Modifier.testTag("live-refresh-${area.name}"), enabled = load.phase != LoadPhase.LOADING && !state.busy)
}

@Composable
private fun LiveDevices(model: ScreenModel, back: () -> Unit) {
    val state by model.state.collectAsState()
    var target by rememberSaveable { mutableStateOf<String?>(null) }
    PhoneScreen("live-devices-screen") {
        ScreenHeading("devices", back)
        LiveLoad(model, Area.DEVICES) {
            if (state.data.devices.isEmpty()) BrandCard { Text("No devices to display.") }
            state.data.devices.forEach { device -> BrandCard {
                Text(device.name + if (device.current) " · this device" else "")
                Text("ID: ${device.id}")
                Text("Added: ${device.added}")
                Text("Last login: ${device.lastLogin ?: "unavailable"}")
                Text(if (device.active) "active" else "revoked")
                BrandActionButton("revoke access", { model.clearError(); target = device.id }, Modifier.testTag("live-revoke-${device.id}"), enabled = device.active && !state.busy && state.loads[Area.DEVICES]?.phase == LoadPhase.READY)
            } }
            if (target == null) OperationError(state.error)
        }
    }
    target?.let { id -> ConfirmDialog("revoke access?", "This device will lose account access. Revoking this device ends its current session.", "revoke", state, { target = null }) {
        model.perform(Command.Revoke(id)) { target = null }
    } }
}

@Composable
private fun LiveMessages(model: ScreenModel, back: () -> Unit, navigate: (String) -> Unit) {
    val state by model.state.collectAsState()
    PhoneScreen("live-messages-screen") {
        ScreenHeading("account messages", back)
        LiveLoad(model, Area.MESSAGES) {
            if (state.data.messages.isEmpty()) BrandCard { Text("No unread messages.") }
            state.data.messages.forEach { message -> BrandCard {
                Text(message.title, style = MaterialTheme.typography.titleLarge); Text(message.body)
                Text("Revision ${message.revision}", style = MaterialTheme.typography.bodySmall)
                message.destination?.let { dest -> BrandActionButton(message.actionLabel ?: "view details", {
                    model.perform(Command.Acknowledge(message.id, message.revision)) { navigate(dest) }
                }, Modifier.testTag("message-action-${message.id}"), enabled = !state.busy && state.loads[Area.MESSAGES]?.phase == LoadPhase.READY) }
                BrandActionButton(message.dismissLabel, { model.perform(Command.Acknowledge(message.id, message.revision)) }, Modifier.testTag("live-ack-${message.id}"), enabled = state.loads[Area.MESSAGES]?.phase == LoadPhase.READY, loading = state.busy)
            } }
            OperationError(state.error)
            BrandActionButton("later", back, Modifier.testTag("messages-later"))
        }
    }
}

private fun money(amount: Long, currency: String) = "$currency ${java.math.BigDecimal.valueOf(amount, 2).toPlainString()}"
@Composable
private fun LiveSubscription(model: ScreenModel, back: () -> Unit) {
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
        ScreenHeading("subscription", back)
        LiveLoad(model, Area.BILLING) {
            val billing = state.data.billing
            if (billing != null) BrandCard {
                Text("${billing.plan} · ${billing.status}", style = MaterialTheme.typography.titleLarge)
                Text("Paid until: ${billing.paidUntil ?: "no paid period"}", Modifier.testTag("live-paid-until"))
                Text("Auto-renewal: ${if (billing.autoRenew) "on" else "off"}")
                Text("Payment method: ${billing.method ?: "none"}")
                Text("Current price: ${billing.currentPrice ?: "unavailable"}")
                Text("Provider: ${billing.mode}", Modifier.testTag("provider-mode"))
                if (billing.mode != "LIVE" || !billing.available) Text("Payment actions are unavailable. No payment provider will be opened.")
                listOf("RUB", "USD").forEach { code -> BrandActionButton("$code${if (code == currency) " ✓" else ""}", { currency = code; route = if (code == "RUB") "MIR" else "BANK_CARD" }, enabled = !state.busy && !state.data.paymentPending) }
                billing.offers.forEach { offer ->
                    offer.prices[currency]?.let { p -> Text("Premium / month: ${money(p.amount, currency)}${p.original?.let { " (was ${money(it, currency)})" } ?: ""}") }
                }
                billing.routes.forEach { cap ->
                    BrandActionButton("${cap.label}${if (route == cap.id) " ✓" else ""} · ${cap.currencies.joinToString()} · auto-renew: ${cap.recurring.joinToString().ifEmpty { "unavailable" }}", { route = cap.id }, Modifier.testTag("live-route-${cap.id}"), enabled = currency in cap.currencies && !state.busy && !state.data.paymentPending)
                }
                billingActions.forEach { kind ->
                    val purchase = kind in setOf("SUBSCRIBE", "RENEW")
                    val allowedRoute = !purchase || (billing.offers.size == 1 && billing.routes.any { it.id == route && currency in it.currencies })
                    BrandActionButton(kind.lowercase().replace('_', ' '), { model.clearError(); requestId = UUID.randomUUID().toString(); confirmedRevision = billing.revision; action = kind }, Modifier.testTag("live-pay-$kind"), enabled = billing.permits(kind) && allowedRoute && !state.data.paymentPending && !state.data.stale && !state.busy && state.loads[Area.BILLING]?.phase == LoadPhase.READY)
                }
                if (state.data.paymentPending) {
                    Text("An operation needs confirmation. Refresh its status before starting another.")
                    BrandActionButton("check operation", { model.perform(Command.ConfirmPayment) }, Modifier.testTag("live-check-payment"), loading = state.busy)
                    BrandActionButton("retry original operation", { model.perform(Command.Payment(requestId, "RENEW", route, currency)) }, Modifier.testTag("live-retry-payment"), enabled = billing.mode == "LIVE" && billing.available && !state.busy)
                }
                state.data.billingOperation?.let { operation ->
                    Text("Operation ${operation.id}: ${operation.status}")
                    val url = operation.redirect?.let { value -> runCatching { value.toUri().takeIf { it.scheme == "https" && it.host != null && it.userInfo == null && it.fragment == null && it.port in setOf(-1,443) } }.getOrNull() }
                    if (url != null && operation.status == "PENDING") BrandActionButton("continue with payment provider", {
                        runCatching { context.startActivity(Intent(Intent.ACTION_VIEW, url)) }
                    }, enabled = billing.mode == "LIVE" && billing.available)
                }
                if (action == null) OperationError(state.error)
            }
        }
    }
    action?.let { kind -> ConfirmDialog("${kind.lowercase().replace('_', ' ')}?", "Review the displayed price and currency. Cancel/change method preserve your paid period. Payments require an available LIVE provider.", "confirm", state, { action = null }) {
        model.perform(Command.Payment(requestId, kind, route, currency)) { action = null }
    } }
}

@Composable
private fun LiveSupport(model: ScreenModel, draft: SavedStateHandle, back: () -> Unit) {
    val state by model.state.collectAsState()
    val subject by draft.getStateFlow("subject", "").collectAsState()
    val description by draft.getStateFlow("description", "").collectAsState()
    val email by draft.getStateFlow("email", state.data.email).collectAsState()
    val selected by draft.getStateFlow("selected", arrayListOf<String>()).collectAsState()
    val id by draft.getStateFlow("request-id", UUID.randomUUID().toString()).collectAsState()
    LaunchedEffect(id) { draft["request-id"] = id }
    var discard by rememberSaveable { mutableStateOf(false) }
    var pickerError by remember { mutableStateOf<String?>(null) }
    val context = LocalContext.current
    fun releaseImages() { selected.forEach { value -> runCatching { context.contentResolver.releasePersistableUriPermission(value.toUri(), Intent.FLAG_GRANT_READ_URI_PERMISSION) } } }
    LaunchedEffect(state.data.supportFrozen) { if (state.data.supportFrozen && selected.isNotEmpty()) { releaseImages(); draft["selected"] = arrayListOf<String>() } }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { values ->
        if (values.size + selected.size > 3) pickerError = "Choose at most 3 images."
        else draft["selected"] = ArrayList((selected + values.map { uri ->
            runCatching { context.contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION) }
            uri.toString()
        }).distinct())
    }
    val close = { if (!state.data.supportFrozen && (subject.isNotEmpty() || description.isNotEmpty() || selected.isNotEmpty())) discard = true else back() }
    BackHandler { close() }
    PhoneScreen("live-support-screen") {
        ScreenHeading("help and support", close)
        LaunchedEffect(Unit) { model.load(Area.SUPPORT) }
        BrandCard {
            if (state.data.supportFrozen) {
                Text("Reference: ${state.data.supportReceipt}", Modifier.testTag("live-support-receipt"))
                Text("Status: ${state.data.supportStatus ?: "not yet confirmed"}")
                Text(if (state.data.supportStatus == "SENT") "The support email was sent." else "A delivery is not confirmed until the server reports SENT.")
                BrandActionButton("check status", { model.perform(Command.SupportStatus) }, Modifier.testTag("live-support-status"), loading = state.busy)
                if (state.data.supportAwaiting) BrandActionButton("retry original request", { model.perform(Command.Support(id, subject, description, email, 0)) }, Modifier.testTag("live-support-retry"), loading = state.busy)
                if (state.data.supportStatus in setOf("SENT", "FAILED", "EXPIRED")) BrandActionButton("new request", {
                    model.perform(Command.NewSupport) { draft["subject"] = ""; draft["description"] = ""; draft["selected"] = arrayListOf<String>(); draft["request-id"] = UUID.randomUUID().toString() }
                })
            } else {
                Text("Send a message to PrettyLisaVPN support. Only your text, reply address and selected images are submitted.")
                BrandTextField(subject, { draft["subject"] = it.take(120) }, "Subject", Modifier.testTag("live-support-subject"), enabled = !state.busy)
                BrandTextField(description, { draft["description"] = it.take(4000) }, "Description", Modifier.testTag("live-support-description"), singleLine = false, minLines = 3, enabled = !state.busy)
                BrandTextField(email, { draft["email"] = it.take(254) }, "Reply email", Modifier.testTag("live-support-email"), enabled = !state.busy)
                Text("Selected images: ${selected.size} / 3 · PNG/JPEG/WebP · 5 MB each / 10 MB total")
                BrandActionButton("attach screenshots", { picker.launch(arrayOf("image/png", "image/jpeg", "image/webp")) }, Modifier.testTag("live-support-attach"), enabled = selected.size < 3 && !state.busy)
                if (selected.isNotEmpty()) BrandActionButton("remove selected images", { releaseImages(); draft["selected"] = arrayListOf<String>() }, enabled = !state.busy)
                Text("Technical diagnostics are unavailable for Android.")
                OperationError(pickerError)
                BrandActionButton("send to support", { model.perform(Command.Support(id, subject.trim(), description.trim(), email.trim(), selected.size, selected.toList())) }, Modifier.testTag("live-support-send"), enabled = subject.isNotBlank() && description.isNotBlank() && android.util.Patterns.EMAIL_ADDRESS.matcher(email.trim()).matches(), loading = state.busy)
            }
            OperationError(state.error)
            BrandActionButton("done", close)
        }
    }
    if (discard) ConfirmDialog("discard draft?", "This removes the local draft. Sending or accepted requests are not cancelled by closing this screen.", "discard", state, { discard = false }) { releaseImages(); discard = false; back() }
}
