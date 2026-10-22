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
import com.prettylisavpn.android.R
import com.prettylisavpn.android.BuildConfig
import com.prettylisavpn.android.data.*

/** Auth-only live shell. All unconnected product actions remain explicitly unavailable. */
@Composable
internal fun SessionApp(model: ScreenModel) {
    val tr = strings()
    val state by model.state.collectAsState()
    var otp by rememberSaveable { mutableStateOf(false) }
    var logout by rememberSaveable { mutableStateOf(false) }
    var forget by rememberSaveable { mutableStateOf(false) }
    val sessionLoad = state.loads[Area.SESSION] ?: Load()
    LaunchedEffect(state.data.signedIn) { if (state.data.signedIn) otp = false else logout = false }
    // No saved email/code is sufficient to resume an OTP challenge after process death.
    LaunchedEffect(model.emailDraft) { if (model.emailDraft.isEmpty()) otp = false }
    val modalPresence = remember { ModalPresence() }
    CompositionLocalProvider(LocalModalPresence provides modalPresence) {
    Surface(color = Brand.PurpleHeart, contentColor = Brand.Mercury) {
        Scaffold(containerColor = Brand.PurpleHeart, contentColor = Brand.Mercury,
            modifier = Modifier.imePadding(), contentWindowInsets = WindowInsets.safeDrawing,
            topBar = { AppHeader(fixture = false) },
        ) { padding ->
            Box(Modifier.padding(padding).consumeWindowInsets(padding)) {
                when {
                    sessionLoad.phase in setOf(LoadPhase.IDLE, LoadPhase.LOADING) -> PhoneScreen("session-restoring") {
                        ScreenHeading(tr(R.string.ui_restoring_session))
                        CircularProgressIndicator(color = Brand.Viking)
                    }
                    sessionLoad.phase == LoadPhase.ERROR && !state.data.signedIn -> PhoneScreen("session-unavailable") {
                        ScreenHeading(tr(R.string.ui_session_unavailable))
                        BrandCard {
                            OperationError(sessionLoad.error)
                            BrandActionButton(tr(R.string.ui_retry), { model.load(Area.SESSION) }, Modifier.testTag("restore-retry"))
                            BrandActionButton(tr(R.string.ui_sign_in_again), { forget = true }, Modifier.testTag("restore-forget"))
                            Text(tr(R.string.ui_signing_in_again_removes_credentials_on_this_device_only_it_does_))
                        }
                    }
                    !state.data.signedIn -> AuthScreen(model, otp, { otp = true }, { otp = false; model.clearError() })
                    else -> LiveAccountScreens(model, messageBlocked = logout || forget) { logout = true }
                }
            }
        }
    }
    BackHandler(enabled = otp && !state.data.signedIn && !state.busy) { otp = false; model.clearError() }
    if (logout) ConfirmDialog(tr(R.string.ui_sign_out_54), tr(R.string.ui_end_this_server_session_on_this_device_if_the_network_is_unavaila), tr(R.string.ui_sign_out), state, { logout = false }) {
        model.perform(Command.Logout) { logout = false; model.emailDraft = "" }
    }
    if (forget) ConfirmDialog(tr(R.string.ui_remove_local_session), tr(R.string.ui_this_removes_local_credentials_and_opens_sign_in_it_does_not_conf), tr(R.string.ui_remove_and_sign_in), state, { forget = false }) {
        model.perform(Command.ForgetLocalSession) { forget = false; model.emailDraft = ""; model.load(Area.SESSION) }
    }
    }
}
