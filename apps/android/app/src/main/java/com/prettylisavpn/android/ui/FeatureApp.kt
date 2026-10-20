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
    val tr = LocalStrings.current
    val state by model.state.collectAsState()
    if (!model.enabled) {
        Surface(color = Brand.PurpleHeart, contentColor = Brand.Mercury) {
            PhoneScreen("screen_UNAVAILABLE") {
                ScreenHeading("PrettyLisaVPN")
                Text(tr(R.string.ui_integration_is_unavailable_this_release_build_contains_no_test_da))
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
        topBar = { AppHeader(fixture = true) },
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
                    ScreenHeading(tr(R.string.ui_settings))
                    BrandCard {
                        Action(tr(R.string.ui_subscription), tr(R.string.ui_manage_your_plan_and_payments), "open-subscription") { go("SUBSCRIPTION") }
                        Action(tr(R.string.ui_devices), tr(R.string.ui_manage_account_access), "open-devices") { go("DEVICES") }
                        Action(tr(R.string.ui_sign_out), tr(R.string.ui_end_the_test_session_on_this_device), "logout") { openDialog("logout") }
                    }
                    if (dialog.isEmpty()) OperationError(state.error)
                }
            }
            composable("ABOUT") {
                PhoneScreen("screen_ABOUT") {
                    ScreenHeading(tr(R.string.ui_about))
                    BrandCard {
                        Text("PrettyLisaVPN", style = MaterialTheme.typography.titleLarge)
                        Text(tr(R.string.ui_android_version_0, BuildConfig.VERSION_NAME))
                        Text(tr(R.string.ui_build_0, BuildConfig.SOURCE_SHA.take(12)), Modifier.testTag("build-source"))
                        Text(tr(R.string.ui_backend_unavailable_test_source_no_get_version_performed), color = Brand.Scorpion)
                    }
                    BrandCard {
                        Text(tr(R.string.ui_help_and_support), style = MaterialTheme.typography.titleMedium)
                        Text(tr(R.string.ui_tell_us_what_happened_test_requests_stay_on_this_device))
                        BrandActionButton(tr(R.string.ui_contact_support), { go("SUPPORT") }, Modifier.testTag("open-support"))
                        BrandActionButton(tr(R.string.ui_account_messages), { openDialog("message") }, Modifier.testTag("open-messages"))
                        BrandActionButton(tr(R.string.ui_test_scenarios), { go("SCENARIOS") }, Modifier.testTag("open-scenarios"))
                    }
                    Text(tr(R.string.ui_inspired_by_love_of_my_life_lisa), style = MaterialTheme.typography.bodySmall)
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
                    Text(tr(R.string.ui_at_most_5_active_devices_per_account_dates_below_are_synthetic_ut))
                    if (state.data.devices.isEmpty()) Text(tr(R.string.ui_no_devices_yet), Modifier.testTag("empty-devices"))
                    state.data.devices.forEach { device ->
                        BrandCard(Modifier.testTag("device-${device.id.takeLast(1)}")) {
                            Text(device.name, style = MaterialTheme.typography.titleMedium)
                            Text("id: ${device.id}", style = MaterialTheme.typography.bodySmall)
                            Text(tr(R.string.ui_added_0, device.added))
                            Text(tr(R.string.ui_last_login_0, device.lastLogin ?: tr(R.string.ui_no_data)))
                            if (device.current) Text(tr(R.string.ui_current_device))
                            Text(if (device.active) tr(R.string.ui_active) else tr(R.string.ui_revoked))
                            BrandActionButton(tr(R.string.ui_revoke_access_26), { openDialog("revoke", device.id) }, Modifier.testTag("revoke-${device.id.takeLast(1)}"), enabled = device.active && !state.busy)
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
                    ScreenHeading(tr(R.string.ui_test_scenarios)) { nav.popBackStack() }
                    BrandCard {
                        Text(tr(R.string.ui_debug_only_resets_in_memory_data_no_backend_email_card_or_tunnel_))
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
        "logout" -> ConfirmDialog(tr(R.string.ui_sign_out_54), tr(R.string.ui_only_the_test_session_will_end_an_active_simulation_is_stopped), tr(R.string.ui_sign_out), state, { dialog = "" }) {
            model.perform(Command.Logout) { dialog = ""; model.emailDraft = "" }
        }
        "revoke" -> {
            val device = state.data.devices.find { it.id == target }
            ConfirmDialog(tr(R.string.ui_revoke_access), "${device?.name.orEmpty()}\nid: ${target}\n${if (device?.current == true) tr(R.string.ui_this_test_device_will_be_signed_out) else tr(R.string.ui_this_test_device_will_lose_account_access)}", tr(R.string.ui_yes_revoke), state, { dialog = "" }) {
                model.perform(Command.Revoke(target)) { if (dialog == "revoke") dialog = "" }
            }
        }
        "cancel" -> ConfirmDialog(tr(R.string.ui_cancel_subscription), tr(R.string.ui_access_is_preserved_until_0_auto_renewal_will_stop_test_data_only, state.data.paidUntil), tr(R.string.ui_yes_cancel), state, { dialog = "" }) {
            model.perform(Command.Payment(UUID.randomUUID().toString(), "CANCEL", "", "")) { if (dialog == "cancel") dialog = "" }
        }
        "method" -> ConfirmDialog(tr(R.string.ui_change_payment_method), tr(R.string.ui_simulate_replacing_the_test_method_with_bank_card_the_paid_period), tr(R.string.ui_simulate_replacement), state, { dialog = "" }) {
            model.perform(Command.Payment(UUID.randomUUID().toString(), "CHANGE_METHOD", "BANK_CARD", "USD")) { if (dialog == "method") dialog = "" }
        }
        "connection" -> InformationDialog(tr(R.string.ui_simulated_connection), tr(R.string.ui_no_vpn_tunnel_exists_no_handshake_traffic_routing_ip_change_or_in, state.data.selectedCountry)) { dialog = "" }
        "message" -> {
            if (message == null) InformationDialog(tr(R.string.ui_account_messages), tr(R.string.ui_no_unread_test_messages)) { dialog = "" }
            else AlertDialog(
                modifier = Modifier.testTag("message-dialog"), containerColor = Brand.Mercury,
                title = { Text(message.title) }, text = {
                    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        Text(message.body); OperationError(state.error)
                        BrandActionButton(tr(R.string.ui_view_details), {
                            model.perform(Command.Acknowledge(message.id, message.revision)) {
                                if (dialog == "message") { dialog = ""; message.destination?.takeIf { it in setOf("SUBSCRIPTION", "SETTINGS", "ABOUT") }?.let(::go) }
                            }
                        }, Modifier.testTag("message-action"), loading = state.busy)
                    }
                },
                onDismissRequest = { dialog = ""; later = true; model.clearError() },
                dismissButton = { TextButton(onClick = { dialog = ""; later = true; model.clearError() }) { Text(tr(R.string.ui_later)) } },
                confirmButton = { TextButton(enabled = !state.busy, onClick = { model.perform(Command.Acknowledge(message.id, message.revision)) { if (state.data.messages.size <= 1) dialog = "" } }) { Text(if (state.busy) tr(R.string.ui_saving) else tr(R.string.ui_understood)) } },
            )
        }
    }
}

@Composable
internal fun LoadedPage(model: ScreenModel, area: Area, tag: String, onBack: (() -> Unit)? = null, content: @Composable ColumnScope.() -> Unit) {
    val tr = LocalStrings.current
    val state by model.state.collectAsState()
    val load = state.loads[area] ?: Load()
    LaunchedEffect(area, load.phase) { if (load.phase == LoadPhase.IDLE) model.load(area) }
    PhoneScreen(tag) {
        if (onBack != null) ScreenHeading(tr.area(area), onBack)
        when (load.phase) {
            LoadPhase.IDLE, LoadPhase.LOADING -> BrandCard {
                CircularProgressIndicator(Modifier.size(24.dp).testTag("loading-${area.name}"), color = Brand.PurpleHeart)
                Text(tr(R.string.ui_loading_test_data))
            }
            LoadPhase.ERROR -> BrandCard {
                OperationError(load.error)
                BrandActionButton(tr(R.string.ui_retry), { model.load(area) }, Modifier.testTag("retry-${area.name}"))
            }
            LoadPhase.READY -> {
                if (state.data.stale) BrandCard { Text(tr(R.string.ui_stale_test_snapshot_refresh_before_starting_an_operation), Modifier.testTag("stale-notice")) }
                content()
            }
        }
    }
}

@Composable
internal fun AuthScreen(model: ScreenModel, otp: Boolean, next: () -> Unit, back: () -> Unit) {
    val tr = LocalStrings.current
    val state by model.state.collectAsState()
    var email by remember { mutableStateOf(model.emailDraft) }
    var code by remember { mutableStateOf("") } // Never saved, including Activity recreation.
    var validation by remember { mutableStateOf<Int?>(null) }
    var now by remember { mutableLongStateOf(SystemClock.elapsedRealtime()) }
    LaunchedEffect(otp) { while (otp) { now = SystemClock.elapsedRealtime(); delay(250) } }
    val remaining = ((model.resendAtMillis - now + 999) / 1000).coerceAtLeast(0)
    PhoneScreen(if (otp) "screen_OTP" else "screen_LOGIN") {
        ScreenHeading(if (otp) tr(R.string.ui_enter_the_code) else tr(R.string.ui_sign_in_by_email), if (otp) back else null)
        BrandCard {
            Text(if (model.fixture) {
                if (otp) tr(R.string.ui_test_code_for_0_123456_nothing_was_sent, model.emailDraft) else tr(R.string.ui_use_any_valid_test_email_no_real_otp_email_is_sent)
            } else if (otp) tr(R.string.ui_enter_the_code_sent_to_0, model.emailDraft) else tr(R.string.ui_we_will_email_you_a_one_time_sign_in_code))
            if (otp) BrandTextField(code, { code = it.filter { digit -> digit in '0'..'9' }.take(6); validation = null }, tr(R.string.ui_6_digit_code), Modifier.testTag("otp"), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), error = validation?.let { tr(it) }, enabled = !state.busy)
            else BrandTextField(email, { email = it.take(254); model.emailDraft = email; validation = null }, tr(R.string.ui_email), Modifier.testTag("login-email"), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email), error = validation?.let { tr(it) }, enabled = !state.busy)
            OperationError(state.error)
            if (otp) {
                OtpLink(if (remaining > 0) tr(R.string.ui_resend_in_0_s, remaining) else if (model.fixture) tr(R.string.ui_resend_test_code) else tr(R.string.ui_resend_the_code), {
                    code = ""; model.perform(Command.RequestOtp(model.emailDraft))
                }, Modifier.testTag("otp-resend"), enabled = remaining == 0L && !state.busy)
                if (model.fixture) Text(tr(R.string.ui_123456_success_000000_expired_other_codes_invalid), style = MaterialTheme.typography.bodySmall)
                OtpLink(tr(R.string.ui_change_email), back, Modifier.testTag("change-email"), enabled = !state.busy)
            }
            BrandActionButton(if (otp) { if (model.fixture) tr(R.string.ui_sign_in_to_test_account) else tr(R.string.ui_sign_in) } else tr(R.string.ui_continue), {
                if (otp) {
                    if (code.length != 6) validation = R.string.ui_enter_all_6_digits
                    else model.perform(Command.VerifyOtp(code)) { code = "" }
                } else if (!android.util.Patterns.EMAIL_ADDRESS.matcher(email.trim()).matches()) validation = R.string.ui_enter_a_valid_email
                else {
                    model.emailDraft = email.trim().lowercase()
                    model.perform(Command.RequestOtp(model.emailDraft), next)
                }
            }, Modifier.testTag("auth-submit"), loading = state.busy)

        }
    }
}

@Composable
private fun FixtureHome(state: ScreenState, model: ScreenModel, countries: () -> Unit, details: () -> Unit, subscription: () -> Unit, messages: () -> Unit) {
    val tr = LocalStrings.current
    Image(painterResource(R.drawable.prettylisavpn_logo), "PrettyLisaVPN", contentScale = ContentScale.Fit, colorFilter = ColorFilter.tint(Brand.Mercury), modifier = Modifier.fillMaxWidth().height(96.dp).testTag("brand-logo"))
    BrandCard {
        Text(tr(R.string.ui_where_to_connect), style = MaterialTheme.typography.titleMedium)
        BrandActionButton(if (state.data.selectedCountry == "AUTO") tr(R.string.ui_autopilot) else state.data.countries.find { it.code == state.data.selectedCountry }?.name ?: tr(R.string.ui_unavailable), countries, Modifier.testTag("open-countries"), enabled = !state.busy && !state.data.simulatedConnection)
        BrandActionButton(if (state.data.simulatedConnection) tr(R.string.ui_stop_simulation) else tr(R.string.ui_simulate_connection), { model.perform(Command.ToggleConnection) }, Modifier.testTag("connect"), enabled = !state.data.stale, loading = state.busy)
        Text(if (state.data.simulatedConnection) tr(R.string.ui_simulation_active_not_a_vpn) else tr(R.string.ui_not_connected), Modifier.testTag("connection-status"), style = MaterialTheme.typography.titleSmall)
        Text(tr(R.string.ui_test_mode_does_not_protect_or_route_your_traffic))
        BrandActionButton(tr(R.string.ui_connection_details), details, Modifier.testTag("connection-details"))
        OperationError(state.error)
    }
    BrandCard {
        Text(tr(R.string.ui_account), style = MaterialTheme.typography.titleMedium)
        Text(state.data.email)
        Text(tr(R.string.ui_plan_0, state.data.plan))
        Text(tr(R.string.ui_active_devices_0_5, state.data.devices.count { it.active }), Modifier.testTag("device-count"))
        if (state.data.plan == "Free") Text(tr(R.string.ui_free_preview_1_hour_per_utc_day_no_real_quota_is_consumed))
        BrandActionButton(tr(R.string.ui_subscription), subscription, Modifier.testTag("home-subscription"))
        BrandActionButton(tr(R.string.ui_messages_0, state.data.messages.size), messages, Modifier.testTag("home-messages"))
    }
    LocationCard(model)
    BrandCard {
        Text(tr(R.string.ui_what_to_protect), style = MaterialTheme.typography.titleMedium)
        Text(tr(R.string.ui_all_traffic_preview_only))
        BrandActionButton(tr(R.string.ui_selected_traffic_soon), {}, enabled = false)
        BrandActionButton(tr(R.string.ui_all_except_selected_soon), {}, enabled = false)
    }
}

@Composable
private fun LocationCard(model: ScreenModel) {
    val tr = LocalStrings.current
    val state by model.state.collectAsState()
    val load = state.loads[Area.LOCATION] ?: Load()
    LaunchedEffect(load.phase) { if (load.phase == LoadPhase.IDLE) model.load(Area.LOCATION) }
    BrandCard {
        Text(tr(R.string.ui_current_location), style = MaterialTheme.typography.titleMedium)
        when (load.phase) {
            LoadPhase.LOADING, LoadPhase.IDLE -> Text(tr(R.string.ui_loading_test_location))
            LoadPhase.ERROR -> OperationError(load.error)
            LoadPhase.READY -> Text(tr(R.string.ui_example_location_berlin_germany_nip_192_0_2_10_documentation_rang))
        }
        BrandActionButton(tr(R.string.ui_refresh_location), { model.load(Area.LOCATION) }, Modifier.testTag("refresh-location"), enabled = load.phase != LoadPhase.LOADING)
    }
}

@Composable
private fun ColumnScope.CountryScreen(state: ScreenState, model: ScreenModel, back: () -> Unit) {
    val tr = LocalStrings.current
    var query by rememberSaveable { mutableStateOf("") }
    BrandCard {
        Text(tr(R.string.ui_autopilot_uses_available_nodes_country_selection_requires_premium))
        BrandActionButton(tr(R.string.ui_autopilot), { model.perform(Command.SelectCountry("AUTO"), back) }, Modifier.testTag("country-AUTO"), enabled = !state.busy)
        BrandTextField(query, { query = it }, tr(R.string.ui_search_countries), Modifier.testTag("country-search"))
        val countries = state.data.countries.filter { it.name.contains(query, ignoreCase = true) }
        if (countries.isEmpty()) Text(tr(R.string.ui_no_countries_found), Modifier.testTag("countries-empty"))
        countries.forEach {
            BrandActionButton("${it.name} · ${it.quality}${if (it.code == state.data.selectedCountry) " ✓" else ""}", { model.perform(Command.SelectCountry(it.code), back) }, Modifier.testTag("country-${it.code}"), enabled = it.available && state.data.plan != "Free" && !state.busy)
        }
        OperationError(state.error)
    }
}

@Composable
private fun ColumnScope.SubscriptionScreen(state: ScreenState, model: ScreenModel, payment: () -> Unit, dialog: (String) -> Unit) {
    val tr = LocalStrings.current
    val data = state.data
    BrandCard {
        Text(tr(R.string.ui_your_plan), style = MaterialTheme.typography.titleMedium)
        Text(data.plan, style = MaterialTheme.typography.titleLarge)
        Text(tr(R.string.ui_paid_until_0, data.paidUntil ?: tr(R.string.ui_no_paid_period)), Modifier.testTag("paid-until"))
        if (data.plan == "Platinum") Text(tr(R.string.ui_manually_assigned_premium_capabilities_no_purchase_needed))
        Text(tr(R.string.ui_auto_renewal_0, if (data.autoRenew) tr(R.string.ui_on) else tr(R.string.ui_off)), Modifier.testTag("auto-renewal"))
        Text(tr(R.string.ui_payment_method_0, data.paymentMethod ?: tr(R.string.ui_none)))
        Text(tr(R.string.ui_test_provider_only_real_payment_actions_are_unavailable), color = Brand.Scorpion)
        Text(tr(R.string.ui_example_offer_rub_100_00_usd_5_00_per_30_day_test_period_these_ar))
        BrandActionButton(tr(R.string.ui_preview_payment_routes), payment, Modifier.testTag("open-payment"), enabled = data.plan != "Platinum" && !data.paymentPending)
        BrandActionButton(tr(R.string.ui_simulate_method_change), { dialog("method") }, Modifier.testTag("change-method"), enabled = data.paymentMethod != null && !data.paymentPending && !state.busy)
        BrandActionButton(tr(R.string.ui_simulate_cancellation), { dialog("cancel") }, Modifier.testTag("cancel-subscription"), enabled = data.autoRenew && !data.paymentPending && !state.busy)
        if (data.paymentPending) {
            Text(tr(R.string.ui_waiting_for_test_provider_confirmation), Modifier.testTag("payment-pending"))
            BrandActionButton(tr(R.string.ui_simulate_confirmation), { model.perform(Command.ConfirmPayment) }, Modifier.testTag("confirm-payment"), loading = state.busy)
        }
        OperationError(state.error)
        BrandActionButton(tr(R.string.ui_refresh), { model.load(Area.BILLING) }, Modifier.testTag("refresh-billing"), enabled = !state.busy)
    }
}

@Composable
private fun PaymentScreen(state: ScreenState, model: ScreenModel, back: () -> Unit) {
    val tr = LocalStrings.current
    var currency by rememberSaveable { mutableStateOf("RUB") }
    var route by rememberSaveable { mutableStateOf("MIR") }
    val operationId = rememberSaveable { UUID.randomUUID().toString() }
    val cap = state.data.routes.find { it.id == route && currency in it.currencies }
    PhoneScreen("screen_PAYMENT") {
        ScreenHeading(tr(R.string.ui_how_to_pay_test_preview), back)
        BrandCard {
            Text(tr(R.string.ui_no_browser_or_payment_service_will_open_no_money_is_charged))
            listOf("RUB", "USD").forEach { code ->
                BrandActionButton("${code}${if (currency == code) " ✓" else ""}", { currency = code; route = if (code == "RUB") "MIR" else "BANK_CARD" }, Modifier.testTag("currency-${code}"), enabled = !state.busy)
            }
            Text(if (currency == "RUB") tr(R.string.ui_example_rub_100_00_30_days) else tr(R.string.ui_example_usd_5_00_30_days))
            state.data.routes.forEach { item ->
                BrandActionButton("${item.label}${if (item.id == route) " ✓" else ""}", { route = item.id }, Modifier.testTag("route-${item.id}"), enabled = currency in item.currencies && !state.busy)
            }
            Text(if (cap != null && currency in cap.recurring) tr(R.string.ui_auto_renewal_supported_by_this_test_route_cancellation_preserves_) else tr(R.string.ui_one_time_test_payment_no_automatic_charges), Modifier.testTag("recurring-terms"))
            OperationError(state.error)
            BrandActionButton(if (state.data.plan == "Free") tr(R.string.ui_simulate_subscription) else tr(R.string.ui_simulate_renewal), {
                model.perform(Command.Payment(operationId, if (state.data.plan == "Free") "SUBSCRIBE" else "RENEW", route, currency), back)
            }, Modifier.testTag("simulate-payment"), enabled = cap != null && !state.data.stale, loading = state.busy)
        }
    }
}

@Composable
private fun Action(title: String, subtitle: String, tag: String, action: () -> Unit) {
    val tr = LocalStrings.current
    Text(subtitle, style = MaterialTheme.typography.bodySmall, color = Brand.Scorpion)
    BrandActionButton(title, action, Modifier.testTag(tag))
}

@Composable
internal fun OperationError(error: String?) {
    val tr = LocalStrings.current
    if (error != null) Text(tr.error(error), Modifier.testTag("operation-error"), color = Brand.PersianRed, style = MaterialTheme.typography.bodyMedium)
}

@Composable
internal fun ConfirmDialog(title: String, body: String, confirm: String, state: ScreenState, dismiss: () -> Unit, action: () -> Unit) {
    val tr = LocalStrings.current
    AlertDialog(
        modifier = Modifier.testTag("confirmation-dialog"), containerColor = Brand.Mercury,
        onDismissRequest = dismiss, title = { Text(title) },
        text = { Column(verticalArrangement = Arrangement.spacedBy(12.dp)) { Text(body); OperationError(state.error) } },
        confirmButton = { TextButton(onClick = action, enabled = !state.busy, modifier = Modifier.testTag("confirm-dialog")) { Text(if (state.busy) "processing…" else confirm) } },
        dismissButton = { TextButton(onClick = dismiss, modifier = Modifier.testTag("dismiss-dialog")) { Text(tr(R.string.ui_cancel)) } },
    )
}

@Composable
private fun InformationDialog(title: String, body: String, dismiss: () -> Unit) {
    val tr = LocalStrings.current
    AlertDialog(containerColor = Brand.Mercury, onDismissRequest = dismiss, title = { Text(title) }, text = { Text(body) }, confirmButton = { TextButton(onClick = dismiss) { Text(tr(R.string.ui_close)) } })
}
