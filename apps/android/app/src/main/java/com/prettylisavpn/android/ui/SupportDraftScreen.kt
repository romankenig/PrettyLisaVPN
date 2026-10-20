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
    val tr = LocalStrings.current
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
        ScreenHeading(tr(R.string.ui_help_and_support), back)
        BrandCard {
            Text(tr(R.string.ui_test_data_no_support_email_or_attachment_leaves_this_device), color = Brand.Scorpion)
            if (receipt != null) {
                Text(tr(R.string.ui_test_request_accepted), Modifier.testTag("support-receipt"), style = MaterialTheme.typography.titleMedium)
                Text(tr(R.string.ui_reference_0, receipt))
                Text(if (ui.data.supportDelivered) tr(R.string.ui_simulated_delivery_complete_no_email_was_sent) else tr(R.string.ui_queued_in_the_test_source))
                BrandActionButton(tr(R.string.ui_check_test_status), { model.perform(Command.SupportStatus) }, Modifier.testTag("support-status"), loading = ui.busy)
                OperationError(ui.error)
                BrandActionButton(tr(R.string.ui_done), onBack, Modifier.testTag("support-done"))
            } else {
                Column(verticalArrangement = Arrangement.spacedBy(20.dp)) {
                    BrandTextField(subject, { state["subject"] = it.take(120) }, stringResource(R.string.subject), Modifier.testTag("support-subject"), keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences, imeAction = ImeAction.Next), enabled = !ui.busy)
                    BrandTextField(description, { state["description"] = it.take(4000) }, stringResource(R.string.description), Modifier.testTag("support-description"), singleLine = false, minLines = 3, keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences), enabled = !ui.busy)
                    BrandTextField(email, { state["email"] = it.take(254) }, stringResource(R.string.reply_email), Modifier.testTag("support-email"), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email, imeAction = ImeAction.Done), error = if (invalidEmail) stringResource(R.string.invalid_email) else null, enabled = !ui.busy)
                }
                Text(tr(R.string.ui_synthetic_screenshots_0_3_each_is_a_1_kb_sample_no_file_picker_or, attachments))
                BrandActionButton(tr(R.string.ui_add_test_screenshot), { state["attachments"] = attachments + 1 }, Modifier.testTag("support-attach"), enabled = attachments < 3 && !ui.busy)
                if (attachments > 0) BrandActionButton(tr(R.string.ui_remove_test_screenshot), { state["attachments"] = attachments - 1 }, Modifier.testTag("support-remove"), enabled = !ui.busy)
                BrandActionButton(tr(R.string.ui_technical_diagnostics_unavailable_on_android), {}, enabled = false)
                OperationError(ui.error)
                BrandActionButton(tr(R.string.ui_simulate_send), {
                    model.perform(Command.Support(requestId, subject.trim(), description.trim(), email.trim(), attachments))
                }, Modifier.testTag("support-send"), enabled = subject.isNotBlank() && description.isNotBlank() && email.isNotBlank() && !invalidEmail, loading = ui.busy)
            }
        }
    }
    if (closing) ConfirmDialog(tr(R.string.ui_discard_draft), tr(R.string.ui_this_local_draft_will_be_removed_an_accepted_test_request_is_not_), tr(R.string.ui_discard), ui, { closing = false }) { closing = false; onBack() }
}
