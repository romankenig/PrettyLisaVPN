package com.prettylisavpn.android.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.ButtonDefaults
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import android.content.Intent
import androidx.core.net.toUri
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.compose.ui.text.LinkAnnotation
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextLinkStyles
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.withLink
import androidx.compose.ui.text.style.TextDecoration
import com.prettylisavpn.android.BuildConfig
import com.prettylisavpn.android.R

/** Windows About content, shared by live and isolated fixture navigation. */
@Composable
internal fun AboutScreen(tag: String, support: () -> Unit, supportTag: String = "about-support", navigate: (String) -> Unit = {}) {
    val tr = strings()
    val context = LocalContext.current
    val language by LocalPresentation.current.preference.language.collectAsState()
    var linkFailed by remember { mutableStateOf(false) }
    val backend by LocalPresentation.current.version.collectAsState()
    BoxWithConstraints(Modifier.fillMaxSize()) {
        Column(
            Modifier.fillMaxWidth().testTag(tag).verticalScroll(rememberScrollState())
                .heightIn(min = maxHeight).padding(20.dp),
            verticalArrangement = Arrangement.SpaceBetween,
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(20.dp)) {
                ScreenHeading(tr(R.string.about_title))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(24.dp)) {
                    AboutVersion(tr(R.string.about_frontend), BuildConfig.VERSION_NAME, "about-frontend-version", Modifier.weight(1f))
                    AboutVersion(tr(R.string.about_backend), backend ?: tr(R.string.unavailable), "about-backend-version", Modifier.weight(1f))
                }
                BrandCard(Modifier.heightIn(min = 96.dp).testTag("about-faq")) {
                    Text(tr(R.string.about_faq), style = MaterialTheme.typography.titleLarge, modifier = Modifier.testTag("about-faq-title"))
                    val questions = faqEntries
                    var question by rememberSaveable { mutableIntStateOf(0) }
                    var expanded by remember { mutableStateOf(false) }
                    val entry = questions[question]
                    Box(Modifier.fillMaxWidth()) {
                        OutlinedButton(
                            { expanded = true }, Modifier.fillMaxWidth().testTag("faq-select"),
                            shape = RoundedCornerShape(8.dp),
                            border = BorderStroke(2.dp, Brand.PurpleHeart),
                            colors = ButtonDefaults.outlinedButtonColors(contentColor = Brand.Black),
                            contentPadding = PaddingValues(horizontal = 14.dp, vertical = 12.dp),
                        ) {
                            Text(tr(entry.question), Modifier.weight(1f))
                            Text("⌄", Modifier.padding(start = 10.dp))
                        }
                        DropdownMenu(expanded, { expanded = false }) {
                            questions.forEachIndexed { index, item -> DropdownMenuItem(text = { Text(tr(item.question)) }, onClick = { question = index; expanded = false }, modifier = Modifier.testTag("faq-option-$index")) }
                        }
                    }
                    FaqAnswer(tr(entry.answer)) { index ->
                        if (entry.links[index] == "support") support()
                        else linkFailed = runCatching {
                            context.startActivity(Intent(Intent.ACTION_VIEW, legalDocumentUrl(language.code, "payments").toUri()))
                        }.isFailure
                    }
                    if (linkFailed) Text(tr(R.string.legal_open_failed), color = Brand.PersianRed)
                }
                LegalDocuments()
                BrandCard(Modifier.testTag("about-help")) {
                    Text(tr(R.string.about_support_title), style = MaterialTheme.typography.titleMedium)
                    Text(tr(R.string.about_support_prompt), style = MaterialTheme.typography.bodySmall, color = Brand.Scorpion)
                    BrandActionButton(tr(R.string.about_contact_support), support, Modifier.testTag(supportTag))
                }
            }
            Text(tr(R.string.about_dedication), style = MaterialTheme.typography.bodySmall,
                color = Brand.Mercury.copy(alpha = 0.55f), modifier = Modifier.padding(top = 18.dp).testTag("about-dedication"))
        }
    }
}

@Composable
private fun FaqAnswer(answer: String, followLink: (Int) -> Unit) {
    val content = buildAnnotatedString {
        var start = 0
        Regex("\\[([^\\]]+)\\]").findAll(answer).forEachIndexed { index, match ->
            append(answer.substring(start, match.range.first))
            withLink(LinkAnnotation.Clickable(
                tag = "faq-navigation",
                styles = TextLinkStyles(style = SpanStyle(
                    color = Brand.PurpleHeart, textDecoration = TextDecoration.Underline,
                )),
                linkInteractionListener = { followLink(index) },
            )) { append(match.groupValues[1]) }
            start = match.range.last + 1
        }
        append(answer.substring(start))
    }
    Text(content, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.testTag("faq-answer"))
}

@Composable
private fun AboutVersion(label: String, value: String, tag: String, modifier: Modifier) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(label, style = MaterialTheme.typography.bodySmall, color = Brand.Mercury)
        Text(value, style = MaterialTheme.typography.bodyMedium, color = Brand.Mercury, modifier = Modifier.testTag(tag))
    }
}
