package com.prettylisavpn.android.ui

import android.os.SystemClock
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.*
import com.prettylisavpn.android.BuildConfig
import com.prettylisavpn.android.R
import com.prettylisavpn.android.data.*
import kotlinx.coroutines.delay
import java.util.UUID

@Composable
internal fun FeatureApp(model: ScreenModel) {
    val state by model.state.collectAsState()
    if (!model.enabled) {
        Surface(color = Brand.PurpleHeart, contentColor = Brand.Mercury) {
            PhoneScreen("screen_UNAVAILABLE") {
                ScreenHeading("PrettyLisaVPN")
                Text("Integration is unavailable. This release build contains no test data or VPN adapter.")
            }
        }
        return
    }
    val nav = rememberNavController()
    val entry by nav.currentBackStackEntryAsState()
    val route = entry?.destination?.route ?: "HOME"
    var dialog by rememberSaveable { mutableStateOf("") }
    var target by rememberSaveable { mutableStateOf("") }
    var later by rememberSaveable { mutableStateOf(false) }
    fun openDialog(value: String, id: String = "") { model.clearError(); target = id; dialog = value }
    fun go(value: String) {
        model.clearError()
        nav.navigate(value) { launchSingleTop = true }
    }
    fun tab(value: String) {
        model.clearError()
        nav.navigate(value) {
            popUpTo(nav.graph.findStartDestination().id) { saveState = true }
            launchSingleTop = true
            restoreState = true
        }
    }
    LaunchedEffect(state.data.signedIn, entry) {
        if (entry == null) return@LaunchedEffect
        if (!state.data.signedIn && route !in listOf("LOGIN", "OTP")) {
            dialog = ""
            nav.navigate("LOGIN") { popUpTo(nav.graph.id); launchSingleTop = true }
        } else if (state.data.signedIn && route in listOf("LOGIN", "OTP")) {
            nav.navigate("HOME") { popUpTo(nav.graph.id); launchSingleTop = true }
            later = false
        }
    }
    val contentState = if (dialog.isEmpty()) state else state.copy(error = null)
    Scaffold(
        modifier = Modifier.imePadding(), containerColor = Brand.PurpleHeart, contentColor = Brand.Mercury,
        contentWindowInsets = WindowInsets.safeDrawing,
        topBar = {
            Text(
                "TEST DATA · NO VPN TUNNEL", color = Brand.Viking, style = MaterialTheme.typography.labelSmall,
                modifier = Modifier.fillMaxWidth().background(Brand.Christalle)
                    .windowInsetsPadding(WindowInsets.safeDrawing.only(WindowInsetsSides.Top + WindowInsetsSides.Horizontal))
                    .padding(horizontal = 16.dp, vertical = 6.dp).testTag("test-banner"),
            )
        },
        bottomBar = {
            if (state.data.signedIn && route in listOf("HOME", "SETTINGS", "ABOUT")) {
                PhoneNavigation(route) { tab(it.name) }
            }
        },
    ) { padding ->
        NavHost(nav, "HOME", Modifier.padding(padding).consumeWindowInsets(padding)) {
            composable("HOME") {
                LoadedPage(model, Area.HOME, "screen_HOME") {
                    FixtureHome(contentState, model, { go("COUNTRIES") }, { openDialog("connection") }, { go("SUBSCRIPTION") }, { openDialog("message") })
                }
            }
            composable("SETTINGS") {
                PhoneScreen("screen_SETTINGS") {
                    ScreenHeading("settings")
                    BrandCard {
                        Action("subscription", "Manage your plan and payments", "open-subscription") { go("SUBSCRIPTION") }
                        Action("devices", "Manage account access", "open-devices") { go("DEVICES") }
                        Action("sign out", "End the test session on this device", "logout") { openDialog("logout") }
                    }
                    if (dialog.isEmpty()) OperationError(state.error)
                }
            }
            composable("ABOUT") {
                PhoneScreen("screen_ABOUT") {
                    ScreenHeading("about")
                    BrandCard {
                        Text("PrettyLisaVPN", style = MaterialTheme.typography.titleLarge)
                        Text("Android · version ${BuildConfig.VERSION_NAME}")
                        Text("build: ${BuildConfig.SOURCE_SHA.take(12)}", Modifier.testTag("build-source"))
                        Text("Backend: unavailable — test source, no GET /version performed", color = Brand.Scorpion)
                    }
                    BrandCard {
                        Text("help and support", style = MaterialTheme.typography.titleMedium)
                        Text("Tell us what happened. Test requests stay on this device.")
                        BrandActionButton("contact support", { go("SUPPORT") }, Modifier.testTag("open-support"))
                        BrandActionButton("account messages", { openDialog("message") }, Modifier.testTag("open-messages"))
                        BrandActionButton("test scenarios", { go("SCENARIOS") }, Modifier.testTag("open-scenarios"))
                    }
                    Text("inspired by love of my life, Lisa", style = MaterialTheme.typography.bodySmall)
                }
            }
            composable("LOGIN") { AuthScreen(model, false, { go("OTP") }, { nav.popBackStack() }) }
            composable("OTP") { AuthScreen(model, true, {}, { nav.popBackStack() }) }
            composable("COUNTRIES") {
                LoadedPage(model, Area.COUNTRIES, "screen_COUNTRIES", { nav.popBackStack() }) {
                    CountryScreen(state, model) { nav.popBackStack() }
                }
            }
            composable("DEVICES") {
                LoadedPage(model, Area.DEVICES, "screen_DEVICES", { nav.popBackStack() }) {
                    Text("At most 5 active devices per account. Dates below are synthetic UTC data.")
                    if (state.data.devices.isEmpty()) Text("No devices yet.", Modifier.testTag("empty-devices"))
                    state.data.devices.forEach { device ->
                        BrandCard(Modifier.testTag("device-${device.id.takeLast(1)}")) {
                            Text(device.name, style = MaterialTheme.typography.titleMedium)
                            Text("id: ${device.id}", style = MaterialTheme.typography.bodySmall)
                            Text("Added: ${device.added}")
                            Text("Last login: ${device.lastLogin ?: "no data"}")
                            if (device.current) Text("current device")
                            Text(if (device.active) "active" else "revoked")
                            BrandActionButton("revoke access", { openDialog("revoke", device.id) }, Modifier.testTag("revoke-${device.id.takeLast(1)}"), enabled = device.active && !state.busy)
                        }
                    }
                }
            }
            composable("SUBSCRIPTION") {
                LoadedPage(model, Area.BILLING, "screen_SUBSCRIPTION", { nav.popBackStack() }) {
                    SubscriptionScreen(contentState, model, { go("PAYMENT") }, { openDialog(it) })
                }
            }
            composable("PAYMENT") { paymentEntry ->
                PaymentScreen(state, model) {
                    // A late result belongs to its original page, never to the page underneath it.
                    if (nav.currentBackStackEntry?.id == paymentEntry.id) nav.popBackStack()
                }
            }
            composable("SUPPORT") { support -> SupportDraftScreen(support.savedStateHandle, model) { nav.popBackStack() } }
            composable("SCENARIOS") {
                PhoneScreen("screen_SCENARIOS") {
                    ScreenHeading("test scenarios") { nav.popBackStack() }
                    BrandCard {
                        Text("Debug only. Resets in-memory data; no backend, email, card or tunnel is contacted. After process death the standard test account returns.")
                        Scenario.entries.forEach { scenario ->
                            BrandActionButton(scenario.name.lowercase().replace('_', ' '), {
                                model.configure(scenario)
                                nav.navigate("HOME") { popUpTo("HOME"); launchSingleTop = true }
                            }, Modifier.testTag("scenario-${scenario.name}"), enabled = !state.busy)
                        }
                    }
                }
            }
        }
    }
    BackHandler(enabled = route in listOf("SETTINGS", "ABOUT") && dialog.isEmpty()) { nav.popBackStack("HOME", false) }
    val message = state.data.messages.firstOrNull()
    // A visit starts only after sign-in; baseline launch stays unobstructed for design acceptance.
    if (dialog.isEmpty() && route == "HOME" && state.data.signedIn && !later && model.emailDraft.isNotEmpty() && message != null) {
        LaunchedEffect(message.id) { dialog = "message" }
    }
    when (dialog) {
        "logout" -> ConfirmDialog("sign out?", "Only the test session will end. An active simulation is stopped.", "sign out", state, { dialog = "" }) {
            model.perform(Command.Logout) { dialog = ""; model.emailDraft = "" }
        }
        "revoke" -> {
            val device = state.data.devices.find { it.id == target }
            ConfirmDialog("revoke access?", "${device?.name.orEmpty()}\nid: $target\n${if (device?.current == true) "This test device will be signed out." else "This test device will lose account access."}", "yes, revoke", state, { dialog = "" }) {
                model.perform(Command.Revoke(target)) { if (dialog == "revoke") dialog = "" }
            }
        }
        "cancel" -> ConfirmDialog("cancel subscription?", "Access is preserved until ${state.data.paidUntil}. Auto-renewal will stop. Test data only.", "yes, cancel", state, { dialog = "" }) {
            model.perform(Command.Payment(UUID.randomUUID().toString(), "CANCEL", "", "")) { if (dialog == "cancel") dialog = "" }
        }
        "method" -> ConfirmDialog("change payment method?", "Simulate replacing the test method with BANK_CARD. The paid period is preserved. No card is linked.", "simulate replacement", state, { dialog = "" }) {
            model.perform(Command.Payment(UUID.randomUUID().toString(), "CHANGE_METHOD", "BANK_CARD", "USD")) { if (dialog == "method") dialog = "" }
        }
        "connection" -> InformationDialog("simulated connection", "No VPN tunnel exists. No handshake, traffic routing, IP change or internet verification was performed. Protocol preview: WireGuard; selected country: ${state.data.selectedCountry}. Runtime statistics are unavailable.") { dialog = "" }
        "message" -> {
            if (message == null) InformationDialog("account messages", "No unread test messages.") { dialog = "" }
            else AlertDialog(
                modifier = Modifier.testTag("message-dialog"), containerColor = Brand.Mercury,
                title = { Text(message.title) }, text = {
                    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        Text(message.body); OperationError(state.error)
                        BrandActionButton("view details", {
                            model.perform(Command.Acknowledge(message.id, message.revision)) {
                                if (dialog == "message") { dialog = ""; message.destination?.takeIf { it in setOf("SUBSCRIPTION", "SETTINGS", "ABOUT") }?.let(::go) }
                            }
                        }, Modifier.testTag("message-action"), loading = state.busy)
                    }
                },
                onDismissRequest = { dialog = ""; later = true; model.clearError() },
                dismissButton = { TextButton(onClick = { dialog = ""; later = true; model.clearError() }) { Text("later") } },
                confirmButton = { TextButton(enabled = !state.busy, onClick = { model.perform(Command.Acknowledge(message.id, message.revision)) { if (state.data.messages.size <= 1) dialog = "" } }) { Text(if (state.busy) "saving…" else "understood") } },
            )
        }
    }
}

@Composable
internal fun LoadedPage(model: ScreenModel, area: Area, tag: String, onBack: (() -> Unit)? = null, content: @Composable ColumnScope.() -> Unit) {
    val state by model.state.collectAsState()
    val load = state.loads[area] ?: Load()
    LaunchedEffect(area, load.phase) { if (load.phase == LoadPhase.IDLE) model.load(area) }
    PhoneScreen(tag) {
        if (onBack != null) ScreenHeading(area.name.lowercase(), onBack)
        when (load.phase) {
            LoadPhase.IDLE, LoadPhase.LOADING -> BrandCard {
                CircularProgressIndicator(Modifier.size(24.dp).testTag("loading-${area.name}"), color = Brand.PurpleHeart)
                Text("Loading test data…")
            }
            LoadPhase.ERROR -> BrandCard {
                OperationError(load.error)
                BrandActionButton("retry", { model.load(area) }, Modifier.testTag("retry-${area.name}"))
            }
            LoadPhase.READY -> {
                if (state.data.stale) BrandCard { Text("Stale test snapshot. Refresh before starting an operation.", Modifier.testTag("stale-notice")) }
                content()
            }
        }
    }
}

@Composable
internal fun AuthScreen(model: ScreenModel, otp: Boolean, next: () -> Unit, back: () -> Unit) {
    val state by model.state.collectAsState()
    var email by remember { mutableStateOf(model.emailDraft) }
    var code by remember { mutableStateOf("") } // Never saved, including Activity recreation.
    var validation by remember { mutableStateOf<String?>(null) }
    var now by remember { mutableLongStateOf(SystemClock.elapsedRealtime()) }
    LaunchedEffect(otp) { while (otp) { now = SystemClock.elapsedRealtime(); delay(250) } }
    val remaining = ((model.resendAtMillis - now + 999) / 1000).coerceAtLeast(0)
    PhoneScreen(if (otp) "screen_OTP" else "screen_LOGIN") {
        ScreenHeading(if (otp) "enter the code" else "sign in by email", if (otp) back else null)
        BrandCard {
            Text(if (model.fixture) {
                if (otp) "Test code for ${model.emailDraft}: 123456. Nothing was sent." else "Use any valid test email. No real OTP email is sent."
            } else if (otp) "Enter the code sent to ${model.emailDraft}." else "We will email you a one-time sign-in code.")
            if (otp) BrandTextField(code, { code = it.filter { digit -> digit in '0'..'9' }.take(6); validation = null }, "6-digit code", Modifier.testTag("otp"), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), error = validation, enabled = !state.busy)
            else BrandTextField(email, { email = it.take(254); model.emailDraft = email; validation = null }, "Email", Modifier.testTag("login-email"), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email), error = validation, enabled = !state.busy)
            OperationError(state.error)
            BrandActionButton(if (otp) { if (model.fixture) "sign in to test account" else "sign in" } else "continue", {
                if (otp) {
                    if (code.length != 6) validation = "Enter all 6 digits."
                    else model.perform(Command.VerifyOtp(code)) { code = "" }
                } else if (!android.util.Patterns.EMAIL_ADDRESS.matcher(email.trim()).matches()) validation = "Enter a valid email."
                else {
                    model.emailDraft = email.trim().lowercase()
                    model.perform(Command.RequestOtp(model.emailDraft), next)
                }
            }, Modifier.testTag("auth-submit"), loading = state.busy)
            if (otp) {
                BrandActionButton(if (remaining > 0) "resend in ${remaining}s" else if (model.fixture) "resend test code" else "resend code", {
                    code = ""; model.perform(Command.RequestOtp(model.emailDraft))
                }, Modifier.testTag("otp-resend"), enabled = remaining == 0L && !state.busy)
                if (model.fixture) Text("123456: success · 000000: expired · other codes: invalid", style = MaterialTheme.typography.bodySmall)
                BrandActionButton("change email", back, Modifier.testTag("change-email"), enabled = !state.busy)
            }
        }
    }
}

@Composable
private fun FixtureHome(state: ScreenState, model: ScreenModel, countries: () -> Unit, details: () -> Unit, subscription: () -> Unit, messages: () -> Unit) {
    Image(painterResource(R.drawable.prettylisavpn_logo), "PrettyLisaVPN", contentScale = ContentScale.Fit, colorFilter = ColorFilter.tint(Brand.Mercury), modifier = Modifier.fillMaxWidth().height(96.dp).testTag("brand-logo"))
    BrandCard {
        Text("where to connect", style = MaterialTheme.typography.titleMedium)
        BrandActionButton(if (state.data.selectedCountry == "AUTO") "autopilot" else state.data.countries.find { it.code == state.data.selectedCountry }?.name ?: "unavailable", countries, Modifier.testTag("open-countries"), enabled = !state.busy && !state.data.simulatedConnection)
        BrandActionButton(if (state.data.simulatedConnection) "stop simulation" else "simulate connection", { model.perform(Command.ToggleConnection) }, Modifier.testTag("connect"), enabled = !state.data.stale, loading = state.busy)
        Text(if (state.data.simulatedConnection) "SIMULATION ACTIVE — NOT A VPN" else "not connected", Modifier.testTag("connection-status"), style = MaterialTheme.typography.titleSmall)
        Text("Test mode does not protect or route your traffic.")
        BrandActionButton("connection details", details, Modifier.testTag("connection-details"))
        OperationError(state.error)
    }
    BrandCard {
        Text("account", style = MaterialTheme.typography.titleMedium)
        Text(state.data.email)
        Text("Plan: ${state.data.plan}")
        Text("Active devices: ${state.data.devices.count { it.active }} / 5", Modifier.testTag("device-count"))
        if (state.data.plan == "Free") Text("Free preview: 1 hour per UTC day. No real quota is consumed.")
        BrandActionButton("subscription", subscription, Modifier.testTag("home-subscription"))
        BrandActionButton("messages (${state.data.messages.size})", messages, Modifier.testTag("home-messages"))
    }
    LocationCard(model)
    BrandCard {
        Text("what to protect", style = MaterialTheme.typography.titleMedium)
        Text("✓ all traffic — preview only")
        BrandActionButton("selected traffic · soon", {}, enabled = false)
        BrandActionButton("all except selected · soon", {}, enabled = false)
    }
}

@Composable
private fun LocationCard(model: ScreenModel) {
    val state by model.state.collectAsState()
    val load = state.loads[Area.LOCATION] ?: Load()
    LaunchedEffect(load.phase) { if (load.phase == LoadPhase.IDLE) model.load(Area.LOCATION) }
    BrandCard {
        Text("current location", style = MaterialTheme.typography.titleMedium)
        when (load.phase) {
            LoadPhase.LOADING, LoadPhase.IDLE -> Text("Loading test location…")
            LoadPhase.ERROR -> OperationError(load.error)
            LoadPhase.READY -> Text("Example location: Berlin, Germany\nIP: 192.0.2.10 (documentation range)\nSynthetic data; your actual IP is unknown.")
        }
        BrandActionButton("refresh location", { model.load(Area.LOCATION) }, Modifier.testTag("refresh-location"), enabled = load.phase != LoadPhase.LOADING)
    }
}

@Composable
private fun ColumnScope.CountryScreen(state: ScreenState, model: ScreenModel, back: () -> Unit) {
    var query by rememberSaveable { mutableStateOf("") }
    BrandCard {
        Text("Autopilot uses available nodes. Country selection requires Premium or Platinum.")
        BrandActionButton("autopilot", { model.perform(Command.SelectCountry("AUTO"), back) }, Modifier.testTag("country-AUTO"), enabled = !state.busy)
        BrandTextField(query, { query = it }, "search countries", Modifier.testTag("country-search"))
        val countries = state.data.countries.filter { it.name.contains(query, ignoreCase = true) }
        if (countries.isEmpty()) Text("No countries found.", Modifier.testTag("countries-empty"))
        countries.forEach {
            BrandActionButton("${it.name} · ${it.quality}${if (it.code == state.data.selectedCountry) " ✓" else ""}", { model.perform(Command.SelectCountry(it.code), back) }, Modifier.testTag("country-${it.code}"), enabled = it.available && state.data.plan != "Free" && !state.busy)
        }
        OperationError(state.error)
    }
}

@Composable
private fun ColumnScope.SubscriptionScreen(state: ScreenState, model: ScreenModel, payment: () -> Unit, dialog: (String) -> Unit) {
    val data = state.data
    BrandCard {
        Text("your plan", style = MaterialTheme.typography.titleMedium)
        Text(data.plan, style = MaterialTheme.typography.titleLarge)
        Text("Paid until: ${data.paidUntil ?: "no paid period"}", Modifier.testTag("paid-until"))
        if (data.plan == "Platinum") Text("Manually assigned. Premium capabilities; no purchase needed.")
        Text("Auto-renewal: ${if (data.autoRenew) "on" else "off"}", Modifier.testTag("auto-renewal"))
        Text("Payment method: ${data.paymentMethod ?: "none"}")
        Text("TEST PROVIDER ONLY. Real payment actions are unavailable.", color = Brand.Scorpion)
        Text("Example offer: RUB 100.00 / USD 5.00 per 30-day test period. These are not commercial prices.")
        BrandActionButton("preview payment routes", payment, Modifier.testTag("open-payment"), enabled = data.plan != "Platinum" && !data.paymentPending)
        BrandActionButton("simulate method change", { dialog("method") }, Modifier.testTag("change-method"), enabled = data.paymentMethod != null && !data.paymentPending && !state.busy)
        BrandActionButton("simulate cancellation", { dialog("cancel") }, Modifier.testTag("cancel-subscription"), enabled = data.autoRenew && !data.paymentPending && !state.busy)
        if (data.paymentPending) {
            Text("Waiting for test provider confirmation.", Modifier.testTag("payment-pending"))
            BrandActionButton("simulate confirmation", { model.perform(Command.ConfirmPayment) }, Modifier.testTag("confirm-payment"), loading = state.busy)
        }
        OperationError(state.error)
        BrandActionButton("refresh", { model.load(Area.BILLING) }, Modifier.testTag("refresh-billing"), enabled = !state.busy)
    }
}

@Composable
private fun PaymentScreen(state: ScreenState, model: ScreenModel, back: () -> Unit) {
    var currency by rememberSaveable { mutableStateOf("RUB") }
    var route by rememberSaveable { mutableStateOf("MIR") }
    val operationId = rememberSaveable { UUID.randomUUID().toString() }
    val cap = state.data.routes.find { it.id == route && currency in it.currencies }
    PhoneScreen("screen_PAYMENT") {
        ScreenHeading("how to pay — test preview", back)
        BrandCard {
            Text("No browser or payment service will open. No money is charged.")
            listOf("RUB", "USD").forEach { code ->
                BrandActionButton("$code${if (currency == code) " ✓" else ""}", { currency = code; route = if (code == "RUB") "MIR" else "BANK_CARD" }, Modifier.testTag("currency-$code"), enabled = !state.busy)
            }
            Text(if (currency == "RUB") "Example: RUB 100.00 / 30 days" else "Example: USD 5.00 / 30 days")
            state.data.routes.forEach { item ->
                BrandActionButton("${item.label}${if (item.id == route) " ✓" else ""}", { route = item.id }, Modifier.testTag("route-${item.id}"), enabled = currency in item.currencies && !state.busy)
            }
            Text(if (cap != null && currency in cap.recurring) "Auto-renewal supported by this test route; cancellation preserves paid access." else "One-time test payment; no automatic charges.", Modifier.testTag("recurring-terms"))
            OperationError(state.error)
            BrandActionButton(if (state.data.plan == "Free") "simulate subscription" else "simulate renewal", {
                model.perform(Command.Payment(operationId, if (state.data.plan == "Free") "SUBSCRIBE" else "RENEW", route, currency), back)
            }, Modifier.testTag("simulate-payment"), enabled = cap != null && !state.data.stale, loading = state.busy)
        }
    }
}

@Composable
private fun Action(title: String, subtitle: String, tag: String, action: () -> Unit) {
    Text(subtitle, style = MaterialTheme.typography.bodySmall, color = Brand.Scorpion)
    BrandActionButton(title, action, Modifier.testTag(tag))
}

@Composable
internal fun OperationError(error: String?) {
    if (error != null) Text(error, Modifier.testTag("operation-error"), color = Brand.PersianRed, style = MaterialTheme.typography.bodyMedium)
}

@Composable
internal fun ConfirmDialog(title: String, body: String, confirm: String, state: ScreenState, dismiss: () -> Unit, action: () -> Unit) {
    AlertDialog(
        modifier = Modifier.testTag("confirmation-dialog"), containerColor = Brand.Mercury,
        onDismissRequest = dismiss, title = { Text(title) },
        text = { Column(verticalArrangement = Arrangement.spacedBy(12.dp)) { Text(body); OperationError(state.error) } },
        confirmButton = { TextButton(onClick = action, enabled = !state.busy, modifier = Modifier.testTag("confirm-dialog")) { Text(if (state.busy) "processing…" else confirm) } },
        dismissButton = { TextButton(onClick = dismiss, modifier = Modifier.testTag("dismiss-dialog")) { Text("cancel") } },
    )
}

@Composable
private fun InformationDialog(title: String, body: String, dismiss: () -> Unit) {
    AlertDialog(containerColor = Brand.Mercury, onDismissRequest = dismiss, title = { Text(title) }, text = { Text(body) }, confirmButton = { TextButton(onClick = dismiss) { Text("close") } })
}
