package com.prettylisavpn.android.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import com.prettylisavpn.android.R
import com.prettylisavpn.android.vpn.*

@Composable
internal fun VpnControls(actions: VpnActions?, country: String, signedIn: Boolean) {
    val tr = strings()
    val status by (actions?.status ?: remember { kotlinx.coroutines.flow.MutableStateFlow(VpnStatus()) }).collectAsState()
    val active = status.phase in setOf(VpnPhase.CONNECTING, VpnPhase.CONNECTED)
    BrandActionButton(tr(if (status.phase == VpnPhase.CONNECTING) R.string.vpn_cancel else if (active) R.string.vpn_disconnect else R.string.dash_connect), {
        if (active) actions?.disconnect() else actions?.connect(country)
    }, Modifier.testTag("home-connect"), enabled = actions != null && signedIn && status.phase != VpnPhase.DISCONNECTING)
    Text(tr(when(status.phase) {
        VpnPhase.CONNECTED -> R.string.vpn_connected
        VpnPhase.CONNECTING -> R.string.vpn_connecting
        VpnPhase.DISCONNECTING -> R.string.vpn_disconnecting
        else -> R.string.ui_not_connected
    }), Modifier.testTag("vpn-status").semantics { liveRegion = LiveRegionMode.Polite }, style = MaterialTheme.typography.titleMedium)
    Text(tr(R.string.vpn_placeholder_notice), Modifier.testTag("vpn-placeholder-notice"), style = MaterialTheme.typography.bodySmall)
    if (status.phase == VpnPhase.CONNECTING) status.attempt?.let { attempt ->
        Text(if (attempt.previousMethod == null) tr(R.string.vpn_trying_method, attempt.method.shortLabel)
            else tr(R.string.vpn_switching_method, attempt.previousMethod.shortLabel, attempt.method.shortLabel),
            Modifier.testTag("vpn-attempt").semantics { liveRegion = LiveRegionMode.Polite }, style = MaterialTheme.typography.bodySmall)
    }
    if (status.phase == VpnPhase.CONNECTED) status.method?.let {
        Text(it.label, Modifier.testTag("vpn-method"), style = MaterialTheme.typography.bodyMedium)
    }
    if (status.error != null) Text(
        if (status.error == VpnError.METHODS_EXHAUSTED) tr(R.string.vpn_placeholder_exhausted, status.method?.label ?: "")
        else tr(R.string.vpn_failed), Modifier.testTag("vpn-error"), style = MaterialTheme.typography.bodySmall, color = Brand.PersianRed)
}
