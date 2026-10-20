package com.prettylisavpn.android.ui

import android.util.Patterns
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.lifecycle.SavedStateHandle
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.prettylisavpn.android.R
import com.prettylisavpn.android.data.Command
import com.prettylisavpn.android.data.ScreenModel
import java.util.UUID

/** Navigation-entry draft, synthetic attachments and a debug-only local receipt. No sender. */
@Composable
internal fun SupportDraftScreen(state: SavedStateHandle, model: ScreenModel, onBack: () -> Unit) {
    val subject by state.getStateFlow("subject", "").collectAsState()
    val description by state.getStateFlow("description", "").collectAsState()
    val email by state.getStateFlow("email", "").collectAsState()
    val attachments by state.getStateFlow("attachments", 0).collectAsState()
    val requestId by state.getStateFlow("request-id", UUID.randomUUID().toString()).collectAsState()
    LaunchedEffect(requestId) { state["request-id"] = requestId }
    val ui by model.state.collectAsState()
    val receipt = ui.data.supportReceipt?.takeIf { it == requestId }
    var closing by rememberSaveable { mutableStateOf(false) }
    val dirty = subject.isNotEmpty() || description.isNotEmpty() || email.isNotEmpty() || attachments > 0
    val back = { if (dirty && receipt == null) closing = true else onBack() }
    BackHandler { back() }
    val invalidEmail = email.isNotBlank() && !Patterns.EMAIL_ADDRESS.matcher(email).matches()
    PhoneScreen("screen_SUPPORT") {
        ScreenHeading("help and support", back)
        BrandCard {
            Text("TEST DATA. No support email or attachment leaves this device.", color = Brand.Scorpion)
            if (receipt != null) {
                Text("Test request accepted", Modifier.testTag("support-receipt"), style = MaterialTheme.typography.titleMedium)
                Text("Reference: $receipt")
                Text(if (ui.data.supportDelivered) "Simulated delivery complete — no email was sent." else "Queued in the test source.")
                BrandActionButton("check test status", { model.perform(Command.SupportStatus) }, Modifier.testTag("support-status"), loading = ui.busy)
                OperationError(ui.error)
                BrandActionButton("done", onBack, Modifier.testTag("support-done"))
            } else {
                Column(verticalArrangement = Arrangement.spacedBy(20.dp)) {
                    BrandTextField(subject, { state["subject"] = it.take(120) }, stringResource(R.string.subject), Modifier.testTag("support-subject"), keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences, imeAction = ImeAction.Next))
                    BrandTextField(description, { state["description"] = it.take(4000) }, stringResource(R.string.description), Modifier.testTag("support-description"), singleLine = false, minLines = 3, keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences))
                    BrandTextField(email, { state["email"] = it.take(254) }, stringResource(R.string.reply_email), Modifier.testTag("support-email"), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email, imeAction = ImeAction.Done), error = if (invalidEmail) stringResource(R.string.invalid_email) else null)
                }
                Text("Synthetic screenshots: $attachments / 3. Each is a 1 KB sample; no file picker or private file access.")
                BrandActionButton("add test screenshot", { state["attachments"] = attachments + 1 }, Modifier.testTag("support-attach"), enabled = attachments < 3 && !ui.busy)
                if (attachments > 0) BrandActionButton("remove test screenshot", { state["attachments"] = attachments - 1 }, Modifier.testTag("support-remove"), enabled = !ui.busy)
                BrandActionButton("technical diagnostics · unavailable on Android", {}, enabled = false)
                OperationError(ui.error)
                BrandActionButton("simulate send", {
                    model.perform(Command.Support(requestId, subject.trim(), description.trim(), email.trim(), attachments))
                }, Modifier.testTag("support-send"), enabled = subject.isNotBlank() && description.isNotBlank() && email.isNotBlank() && !invalidEmail, loading = ui.busy)
            }
        }
    }
    if (closing) ConfirmDialog("discard draft?", "This local draft will be removed. An accepted test request is not cancelled by closing the screen.", "discard", ui, { closing = false }) { closing = false; onBack() }
}
