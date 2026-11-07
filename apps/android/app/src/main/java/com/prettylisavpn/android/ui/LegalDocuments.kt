package com.prettylisavpn.android.ui

import android.content.Intent
import androidx.core.net.toUri
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import com.prettylisavpn.android.R

internal val legalDocuments = listOf(
    Triple("terms", R.string.legal_terms, "📄"),
    Triple("privacy", R.string.legal_privacy, "🔐"),
    Triple("refunds", R.string.legal_refunds, "↩️"),
    Triple("payments", R.string.legal_payments, "💳"),
)

internal fun legalDocumentUrl(language: String, document: String): String {
    require(document in legalDocuments.map { it.first })
    require(language in setOf("ru", "en", "de", "fr", "es", "zh"))
    return "https://prettylisavpn.com" + (if (language == "ru") "" else "/$language") + "/legal/$document/"
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun LegalDocuments(compact: Boolean = false) {
    val tr = strings()
    val context = LocalContext.current
    val language by LocalPresentation.current.preference.language.collectAsState()
    var failed by remember { mutableStateOf(false) }
    fun open(document: String) {
        failed = runCatching { context.startActivity(Intent(Intent.ACTION_VIEW, legalDocumentUrl(language.code, document).toUri())) }.isFailure
    }
    if (compact) Column(Modifier.fillMaxWidth().testTag("auth-documents"), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        FlowRow(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            legalDocuments.forEach { (key, label, _) ->
                TextButton({ open(key) }, Modifier.heightIn(min = 48.dp).testTag("auth-document-$key"), contentPadding = PaddingValues(2.dp),
                    colors = ButtonDefaults.textButtonColors(contentColor = Brand.Mercury.copy(alpha = .85f))) {
                    Text(tr(label), style = MaterialTheme.typography.bodySmall)
                }
            }
        }
        if (failed) Text(tr(R.string.legal_open_failed), style = MaterialTheme.typography.bodySmall)
    } else BrandCard(Modifier.testTag("about-documents")) {
        Text(tr(R.string.legal_documents), style = MaterialTheme.typography.titleLarge)
        Text(tr(R.string.legal_intro), color = Brand.Scorpion, style = MaterialTheme.typography.bodySmall)
        legalDocuments.forEach { (key, label, icon) ->
            Surface(onClick = { open(key) }, Modifier.fillMaxWidth().testTag("about-document-$key"),
                shape = MaterialTheme.shapes.medium, color = Brand.Heliotrope.copy(alpha = .13f), contentColor = Brand.Christalle) {
                Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text(icon)
                    Text(tr(label), Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
                    Text("↗")
                }
            }
        }
        if (failed) Text(tr(R.string.legal_open_failed), color = Brand.PersianRed, style = MaterialTheme.typography.bodySmall)
    }
}
