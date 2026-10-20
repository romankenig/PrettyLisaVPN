package com.prettylisavpn.android.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import com.prettylisavpn.android.BuildConfig
import com.prettylisavpn.android.data.*

/** Auth-only live shell. All unconnected product actions remain explicitly unavailable. */
@Composable
internal fun SessionApp(model: ScreenModel) {
    val state by model.state.collectAsState()
    var otp by rememberSaveable { mutableStateOf(false) }
    var logout by rememberSaveable { mutableStateOf(false) }
    var forget by rememberSaveable { mutableStateOf(false) }
    val sessionLoad = state.loads[Area.SESSION] ?: Load()
    LaunchedEffect(state.data.signedIn) { if (state.data.signedIn) otp = false else logout = false }
    // No saved email/code is sufficient to resume an OTP challenge after process death.
    LaunchedEffect(model.emailDraft) { if (model.emailDraft.isEmpty()) otp = false }
    Surface(color = Brand.PurpleHeart, contentColor = Brand.Mercury) {
        Scaffold(containerColor = Brand.PurpleHeart, contentColor = Brand.Mercury,
            modifier = Modifier.imePadding(), contentWindowInsets = WindowInsets.safeDrawing,
            topBar = {
                Text("DEVELOPMENT API · VPN UNAVAILABLE", style = MaterialTheme.typography.labelSmall,
                    color = Brand.Viking, modifier = Modifier.fillMaxWidth().background(Brand.Christalle)
                        .windowInsetsPadding(WindowInsets.safeDrawing.only(WindowInsetsSides.Top + WindowInsetsSides.Horizontal))
                        .padding(12.dp).testTag("live-banner"))
            },
        ) { padding ->
            Box(Modifier.padding(padding).consumeWindowInsets(padding)) {
                when {
                    sessionLoad.phase in setOf(LoadPhase.IDLE, LoadPhase.LOADING) -> PhoneScreen("session-restoring") {
                        ScreenHeading("restoring session")
                        CircularProgressIndicator(color = Brand.Viking)
                    }
                    sessionLoad.phase == LoadPhase.ERROR && !state.data.signedIn -> PhoneScreen("session-unavailable") {
                        ScreenHeading("session unavailable")
                        BrandCard {
                            OperationError(sessionLoad.error)
                            BrandActionButton("retry", { model.load(Area.SESSION) }, Modifier.testTag("restore-retry"))
                            BrandActionButton("sign in again", { forget = true }, Modifier.testTag("restore-forget"))
                            Text("Signing in again removes credentials on this device only. It does not confirm a server logout.")
                        }
                    }
                    !state.data.signedIn -> AuthScreen(model, otp, { otp = true }, { otp = false; model.clearError() })
                    else -> PhoneScreen("live-account") {
                        ScreenHeading("PrettyLisaVPN")
                        BrandCard {
                            Text(state.data.email, Modifier.testTag("account-email"))
                            Text("Plan: ${state.data.plan}")
                            Text("Active devices: ${state.data.activeDeviceCount} / 5")
                            Text("Account data from development backend. No VPN tunnel is running.")
                            BrandActionButton("refresh account", { model.load(Area.HOME) }, Modifier.testTag("account-refresh"), loading = state.loads[Area.HOME]?.phase == LoadPhase.LOADING)
                            OperationError(state.loads[Area.HOME]?.error)
                            OperationError(state.error)
                            BrandActionButton("sign out", { logout = true }, Modifier.testTag("live-logout"), enabled = !state.busy)
                        }
                        BrandCard {
                            Text("VPN, country selection, payments, support and device management are not connected in this mode.")
                            BrandActionButton("connect VPN · unavailable", {}, enabled = false)
                            Text("Android ${BuildConfig.VERSION_NAME} · ${BuildConfig.SOURCE_SHA.take(12)}")
                        }
                    }
                }
            }
        }
    }
    BackHandler(enabled = otp && !state.data.signedIn && !state.busy) { otp = false; model.clearError() }
    if (logout) ConfirmDialog("sign out?", "End this server session on this device. If the network is unavailable, credentials are retained for retry.", "sign out", state, { logout = false }) {
        model.perform(Command.Logout) { logout = false; model.emailDraft = "" }
    }
    if (forget) ConfirmDialog("remove local session?", "This removes local credentials and opens sign-in. It does not confirm a server logout.", "remove and sign in", state, { forget = false }) {
        model.perform(Command.ForgetLocalSession) { forget = false; model.emailDraft = ""; model.load(Area.SESSION) }
    }
}
