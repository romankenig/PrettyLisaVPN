package com.prettylisavpn.android.ui

import android.Manifest
import android.app.Activity
import android.content.pm.PackageManager
import android.net.VpnService
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import com.prettylisavpn.android.R
import com.prettylisavpn.android.vpn.*

@Composable
internal fun VpnControls(actions: VpnActions?, country: String, signedIn: Boolean) {
    val tr = strings()
    val context = LocalContext.current
    val latestSignedIn by rememberUpdatedState(signedIn)
    val status by (actions?.status ?: remember { kotlinx.coroutines.flow.MutableStateFlow(VpnStatus()) }).collectAsState()
    var waiting by rememberSaveable { mutableStateOf(false) }
    var selected by rememberSaveable { mutableStateOf("AUTO") }
    var denied by rememberSaveable { mutableStateOf(false) }
    val start: () -> Unit = {
        waiting = false
        if (latestSignedIn && VpnService.prepare(context) == null) actions?.connect(selected)
    }
    val notifications = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { start() }
    val consent = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        if (result.resultCode == Activity.RESULT_OK && latestSignedIn && VpnService.prepare(context) == null) {
            if (Build.VERSION.SDK_INT >= 33 && context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED)
                notifications.launch(Manifest.permission.POST_NOTIFICATIONS)
            else start()
        } else { waiting = false; denied = true }
    }
    val active = status.phase in setOf(VpnPhase.RECONCILING, VpnPhase.CONNECTING, VpnPhase.VERIFYING, VpnPhase.CONNECTED)
    val label = if (active) R.string.vpn_disconnect else if (status.phase == VpnPhase.CLEANUP_PENDING) R.string.vpn_retry_cleanup else R.string.dash_connect
    BrandActionButton(tr(label), {
        denied = false
        if (active || status.phase == VpnPhase.CLEANUP_PENDING) actions?.disconnect()
        else {
            selected = country
            val intent = VpnService.prepare(context)
            if (intent == null) {
                waiting = true
                if (Build.VERSION.SDK_INT >= 33 && context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED)
                    notifications.launch(Manifest.permission.POST_NOTIFICATIONS)
                else start()
            } else { waiting = true; consent.launch(intent) }
        }
    }, Modifier.testTag("home-connect"), enabled = actions != null && signedIn && !waiting && status.phase != VpnPhase.DISCONNECTING)
    Text(tr(when(status.phase) {
        VpnPhase.CONNECTED -> R.string.vpn_connected
        VpnPhase.CONNECTING, VpnPhase.RECONCILING -> R.string.vpn_connecting
        VpnPhase.VERIFYING -> R.string.vpn_verifying
        VpnPhase.DISCONNECTING -> R.string.vpn_disconnecting
        VpnPhase.CLEANUP_PENDING -> R.string.vpn_cleanup
        else -> R.string.ui_not_connected
    }), Modifier.testTag("vpn-status"), style = MaterialTheme.typography.titleMedium)
    if (status.phase == VpnPhase.CONNECTED && status.method != null)
        Text(status.method!!.label, Modifier.testTag("vpn-method"), style = MaterialTheme.typography.bodyMedium)
    val error = when {
        denied -> R.string.vpn_permission_denied
        actions == null -> R.string.vpn_unavailable
        else -> when(status.error) {
            VpnError.PERMISSION -> R.string.vpn_permission_denied
            VpnError.UNSUPPORTED -> R.string.vpn_unsupported
            VpnError.VERIFICATION -> R.string.vpn_verification_failed
            VpnError.QUOTA -> R.string.vpn_quota
            VpnError.ACCESS -> R.string.vpn_access
            VpnError.CLEANUP -> R.string.vpn_cleanup
            null -> null
            else -> R.string.vpn_failed
        }
    }
    if (error != null) Text(tr(error), Modifier.testTag("vpn-error"), style = MaterialTheme.typography.bodySmall, color = Brand.PersianRed)
}
