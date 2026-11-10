package com.prettylisavpn.android.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.foundation.layout.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.unit.dp
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.contentDescription
import com.prettylisavpn.android.R
import com.prettylisavpn.android.vpn.*

@Composable
internal fun VpnControls(actions: VpnActions?, country: String, signedIn: Boolean, canConnect: Boolean = true,
    quotaExhausted: Boolean = false, onUpgrade: (() -> Unit)? = null) {
    val tr = strings()
    fun methodName(method: VpnMethod) = if (method.id == "wireguard_relay") tr(R.string.vpn_wireguard_relay) else method.shortLabel
    val status by (actions?.status ?: remember { kotlinx.coroutines.flow.MutableStateFlow(VpnStatus()) }).collectAsState()
    var confirmReset by remember(actions, status.method, status.phase, country, signedIn) { mutableStateOf(false) }
    val canReset = actions != null && signedIn && canConnect && status.error != VpnError.CLEANUP
    val active = status.phase in setOf(VpnPhase.CONNECTING, VpnPhase.CONNECTED, VpnPhase.CHECKING, VpnPhase.WAITING_NETWORK, VpnPhase.RECONNECTING) || status.error == VpnError.CLEANUP
    if (quotaExhausted || status.error == VpnError.FREE_LIMIT) {
        Text(tr(R.string.free_quota_exhausted), Modifier.testTag("free-quota-notice"), style = MaterialTheme.typography.bodyMedium, color = Brand.Christalle)
        if (onUpgrade != null) TextButton(onUpgrade, Modifier.testTag("free-quota-buy")) { Text(tr(R.string.free_quota_buy)) }
    }
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
        BrandActionButton(tr(if (status.phase in setOf(VpnPhase.CONNECTING, VpnPhase.RECONNECTING)) R.string.vpn_cancel else if (active) R.string.vpn_disconnect else R.string.dash_connect), {
            if (active) actions?.disconnect() else if (quotaExhausted && onUpgrade != null) onUpgrade() else actions?.connect(country)
        }, Modifier.weight(1f).testTag("home-connect"), enabled = actions != null && signedIn && (active || canConnect) && status.phase != VpnPhase.DISCONNECTING)
    }
    Text(tr(when(status.phase) {
        VpnPhase.CONNECTED -> R.string.vpn_connected
        VpnPhase.CONNECTING -> R.string.vpn_connecting
        VpnPhase.DISCONNECTING -> R.string.vpn_disconnecting
        VpnPhase.CHECKING -> R.string.vpn_checking
        VpnPhase.WAITING_NETWORK -> R.string.vpn_waiting_network
        VpnPhase.RECONNECTING -> R.string.vpn_reconnecting
        else -> R.string.ui_not_connected
    }), Modifier.testTag("vpn-status").semantics { liveRegion = LiveRegionMode.Polite }, style = MaterialTheme.typography.titleMedium)
    if (status.phase == VpnPhase.CONNECTING) status.attempt?.let { attempt ->
        Text(if (attempt.previousMethod == null) tr(R.string.vpn_trying_method, methodName(attempt.method))
            else tr(R.string.vpn_switching_method, methodName(attempt.previousMethod), methodName(attempt.method)),
            Modifier.testTag("vpn-attempt").semantics { liveRegion = LiveRegionMode.Polite }, style = MaterialTheme.typography.bodySmall)
    }
    if (status.phase in setOf(VpnPhase.CONNECTED, VpnPhase.CHECKING, VpnPhase.WAITING_NETWORK, VpnPhase.RECONNECTING)) status.method?.let {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(methodName(it), Modifier.testTag("vpn-method"), style = MaterialTheme.typography.bodyMedium)
            IconButton({ confirmReset = true }, Modifier.size(40.dp).testTag("vpn-reset-methods"), enabled = canReset) {
                Icon(Icons.Outlined.Refresh, tr(R.string.vpn_reset_methods), Modifier.size(18.dp), tint = Brand.Christalle.copy(alpha = .6f))
            }
        }
        if (confirmReset && canReset) AlertDialog(
            onDismissRequest = { confirmReset = false }, containerColor = Brand.Mercury,
            modifier = Modifier.testTag("vpn-reset-confirmation"),
            title = { Text(tr(R.string.vpn_reset_title)) },
            text = { Text(tr(R.string.vpn_reset_description)) },
            confirmButton = { TextButton({ confirmReset = false; actions?.resetMethods(country) }, Modifier.testTag("vpn-reset-confirm")) { Text(tr(R.string.vpn_reset_confirm)) } },
            dismissButton = { TextButton({ confirmReset = false }, Modifier.testTag("vpn-reset-cancel")) { Text(tr(R.string.ui_cancel)) } },
        )
    }
    if (status.phase == VpnPhase.CONNECTING) Text(tr(R.string.vpn_first_connection_hint),
        Modifier.testTag("vpn-duration-hint"), style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
    if (status.error != null && status.error != VpnError.FREE_LIMIT) Text(
        if (status.error == VpnError.DEMO_LIMIT) tr(R.string.demo_exhausted)
        else if (status.error == VpnError.METHODS_EXHAUSTED) tr(R.string.vpn_placeholder_exhausted, status.method?.label ?: "")
        else tr(if (status.error == VpnError.UNSTABLE) R.string.vpn_unstable else R.string.vpn_failed), Modifier.testTag("vpn-error"), style = MaterialTheme.typography.bodySmall, color = Brand.PersianRed)
}
