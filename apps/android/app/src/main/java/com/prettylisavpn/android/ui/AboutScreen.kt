package com.prettylisavpn.android.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import com.prettylisavpn.android.BuildConfig
import com.prettylisavpn.android.R

/** Windows About content, shared by live and isolated fixture navigation. */
@Composable
internal fun AboutScreen(tag: String, support: () -> Unit, supportTag: String = "about-support") {
    val tr = strings()
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
                // Windows has a heading-only FAQ card; do not invent questions or links.
                BrandCard(Modifier.heightIn(min = 96.dp).testTag("about-faq")) {
                    Text(tr(R.string.about_faq), style = MaterialTheme.typography.titleMedium, modifier = Modifier.testTag("about-faq-title"))
                }
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
private fun AboutVersion(label: String, value: String, tag: String, modifier: Modifier) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(label, style = MaterialTheme.typography.bodySmall, color = Brand.Mercury)
        Text(value, style = MaterialTheme.typography.bodyMedium, color = Brand.Mercury, modifier = Modifier.testTag(tag))
    }
}
