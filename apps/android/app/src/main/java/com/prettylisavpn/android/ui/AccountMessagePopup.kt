package com.prettylisavpn.android.ui

import android.content.Intent
import androidx.core.net.toUri
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.window.DialogProperties
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.prettylisavpn.android.R
import com.prettylisavpn.android.data.*
import java.time.Instant
import kotlinx.coroutines.delay

internal class ModalPresence { var count by mutableIntStateOf(0) }
internal val LocalModalPresence = staticCompositionLocalOf<ModalPresence?> { null }

/** Same visit semantics as Windows: no inbox, one popup, later without ACK, action after ACK. */
@Composable
internal fun AccountMessagePopup(model: ScreenModel, blocked: Boolean, navigate: (String) -> Unit) {
    val context = LocalContext.current
    val state by model.state.collectAsState()
    val seen by model.messageVisit.seen.collectAsState()
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    var started by remember { mutableStateOf(lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) }
    DisposableEffect(lifecycle) {
        val observer = LifecycleEventObserver { _, _ -> started = lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED) }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer) }
    }
    // A successful list is fetched once per signed-in visit. Failed reads retry in foreground.
    LaunchedEffect(model, started) {
        while (started) {
            if (model.state.value.loads[Area.MESSAGES]?.phase in listOf(null, LoadPhase.IDLE, LoadPhase.ERROR) || model.state.value.data.messages.any { !it.dismissible }) model.load(Area.MESSAGES)
            delay(10_000)
        }
    }
    var now by remember { mutableStateOf(Instant.now()) }
    val message = remember(state.data.messages, seen, now) { model.messageVisit.next(state.data.messages, Instant.now()) }
    LaunchedEffect(message?.expiresAt, started) {
        if (!started) return@LaunchedEffect
        val expiry = message?.expiresAt ?: return@LaunchedEffect
        val deadline = Instant.parse(expiry)
        while (Instant.now().isBefore(deadline)) delay(java.time.Duration.between(Instant.now(), deadline).toMillis().coerceIn(1, 86_400_000))
        now = Instant.now()
    }
    if (message == null || !MessageVisit.fresh(message, Instant.now()) || !started || (message.dismissible && (blocked || (LocalModalPresence.current?.count ?: 0) > 0))) return
    val tr = strings()
    var linkError by remember(message.id, message.revision) { mutableStateOf(false) }
    fun later() { if (message.dismissible) { model.messageVisit.defer(message); model.clearError() } }
    fun acknowledge(destination: String? = null) {
        if (!message.dismissible || !MessageVisit.fresh(message, Instant.now()) || state.busy) return
        model.perform(Command.Acknowledge(message.id, message.revision)) {
            model.messageVisit.defer(message)
            if (destination != null && MessageVisit.fresh(message, Instant.now())) navigate(destination)
        }
    }
    key(MessageVisit.key(message)) {
        AlertDialog(
            properties = DialogProperties(dismissOnBackPress = message.dismissible, dismissOnClickOutside = message.dismissible),
            modifier = Modifier.testTag("account-message-popup"), containerColor = Brand.Mercury,
            onDismissRequest = { if (!state.busy) later() },
            title = { Text(message.title) },
            text = { Column(Modifier.heightIn(max = 360.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(message.body)
                message.links.forEachIndexed { index, link ->
                    TextButton({
                        linkError = runCatching {
                            require(validMessageUrl(link.url))
                            context.startActivity(Intent(Intent.ACTION_VIEW, link.url.toUri()).addCategory(Intent.CATEGORY_BROWSABLE))
                        }.isFailure
                    }, modifier = Modifier.testTag("message-link-$index")) { Text(link.label) }
                }
                if (linkError) Text(tr(R.string.message_link_error))
                OperationError(state.error)
                if (state.error != null) TextButton({ model.clearError(); model.load(Area.MESSAGES) }, enabled = !state.busy, modifier = Modifier.testTag("message-refresh")) { Text(tr(R.string.ui_retry)) }
            } },
            confirmButton = { if (message.dismissible) Column {
                message.destination?.let { destination -> TextButton({ acknowledge(destination) }, enabled = !state.busy && state.loads[Area.MESSAGES]?.phase == LoadPhase.READY,
                    modifier = Modifier.testTag("message-action-${message.id}")) { Text(message.actionLabel ?: tr(R.string.ui_view_details)) } }
                TextButton({ acknowledge() }, enabled = !state.busy && state.loads[Area.MESSAGES]?.phase == LoadPhase.READY,
                    modifier = Modifier.testTag("live-ack-${message.id}")) { Text(if (state.busy) tr(R.string.processing) else if (message.dismissLabel == "understood") tr(R.string.ui_understood) else message.dismissLabel) }
            } },
            dismissButton = { if (message.dismissible) TextButton({ later() }, enabled = !state.busy, modifier = Modifier.testTag("messages-later")) { Text(tr(R.string.ui_later)) } },
        )
    }
}
