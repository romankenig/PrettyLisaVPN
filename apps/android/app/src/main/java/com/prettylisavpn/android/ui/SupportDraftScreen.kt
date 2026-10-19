package com.prettylisavpn.android.ui

import android.util.Patterns
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.collectAsState
import androidx.lifecycle.SavedStateHandle
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.prettylisavpn.android.R

/** Local UI only. No sender/diagnostics/attachments until the Android API adapter exists. */
@Composable
internal fun SupportDraftScreen(state: SavedStateHandle, onBack: () -> Unit) {
    // Entry-owned state survives Activity/configuration changes independently of composition.
    // Popping the Support destination removes its state together with the navigation entry.
    val subject by state.getStateFlow("subject", "").collectAsState()
    val description by state.getStateFlow("description", "").collectAsState()
    val email by state.getStateFlow("email", "").collectAsState()
    val invalidEmail = email.isNotBlank() && !Patterns.EMAIL_ADDRESS.matcher(email).matches()
    PhoneScreen("screen_SUPPORT") {
        ScreenHeading(stringResource(R.string.help), onBack)
        BrandCard {
            Text(stringResource(R.string.support_unavailable), style = MaterialTheme.typography.bodyMedium, color = Brand.Scorpion)
            Column(verticalArrangement = Arrangement.spacedBy(20.dp)) {
                BrandTextField(
                    subject, { state["subject"] = it.take(120) }, stringResource(R.string.subject),
                    Modifier.testTag("support-subject"),
                    keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences, imeAction = ImeAction.Next),
                )
                BrandTextField(
                    description, { state["description"] = it.take(4000) }, stringResource(R.string.description),
                    Modifier.testTag("support-description"), singleLine = false, minLines = 3,
                    keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences),
                )
                BrandTextField(
                    email, { state["email"] = it.take(254) }, stringResource(R.string.reply_email),
                    Modifier.testTag("support-email"),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email, imeAction = ImeAction.Done),
                    error = if (invalidEmail) stringResource(R.string.invalid_email) else null,
                )
            }
            BrandActionButton(
                stringResource(R.string.send), onClick = {}, enabled = false,
                modifier = Modifier.testTag("support-send"),
            )
        }
    }
}
