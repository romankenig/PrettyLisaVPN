package com.prettylisavpn.android.ui

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.unit.dp
import com.prettylisavpn.android.R
import com.prettylisavpn.android.data.*
import kotlinx.coroutines.delay
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import java.util.Locale

internal fun readableDate(raw: String?, locale: Locale, zone: ZoneId): String? = raw?.let {
    runCatching { DateTimeFormatter.ofLocalizedDateTime(FormatStyle.MEDIUM, FormatStyle.SHORT).withLocale(locale).withZone(zone).format(Instant.parse(it)) }.getOrNull()
}

@Composable
internal fun DetailValue(label: String, value: String, modifier: Modifier = Modifier) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(3.dp)) {
        Text(label, style = MaterialTheme.typography.bodySmall, color = Brand.Scorpion)
        Text(value, style = MaterialTheme.typography.titleSmall)
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun AccountSummary(data: Snapshot) {
    val tr = strings()
    BrandCard(Modifier.testTag("account-summary")) {
        Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text(tr(R.string.dash_account), style = MaterialTheme.typography.bodySmall, color = Brand.Scorpion)
            Text(data.email, Modifier.testTag("account-email"), style = MaterialTheme.typography.titleSmall)
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(36.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            DetailValue(tr(R.string.dash_plan), data.plan)
            DetailValue(tr(R.string.dash_devices), "${data.activeDeviceCount} / 5", Modifier.testTag("account-device-count"))
        }
    }
}

@Composable
internal fun SettingsOption(title: String, detail: String, icon: Int, tag: String, danger: Boolean = false, enabled: Boolean = true, onClick: () -> Unit) {
    Surface(onClick = onClick, enabled = enabled, modifier = Modifier.fillMaxWidth().testTag(tag), shape = MaterialTheme.shapes.medium,
        color = if (danger) Brand.PersianRed else Brand.Mercury, contentColor = if (danger) androidx.compose.ui.graphics.Color.White else Brand.Black) {
        Row(Modifier.padding(18.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            Icon(painterResource(icon), null, Modifier.size(28.dp))
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(title, style = MaterialTheme.typography.titleSmall)
                Text(detail, style = MaterialTheme.typography.bodySmall)
            }
            if (!danger) Text("→")
        }
    }
}

@Composable
internal fun LiveHome(model: ScreenModel) {
    val tr = strings()
    val state by model.state.collectAsState()
    val presentation = LocalPresentation.current
    val location by presentation.location.collectAsState()
    val language by presentation.preference.language.collectAsState()
    val locale = Locale.forLanguageTag(language.code)
    var selected by rememberSaveable { mutableStateOf("AUTO") }
    var expanded by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) {
        model.load(Area.HOME)
        while (true) { model.load(Area.COUNTRIES); presentation.refreshLocation(); delay(60_000) }
    }
    val collator = remember(locale) { java.text.Collator.getInstance(locale) }
    val countries = state.data.countries.filter { it.available }.sortedWith { a, b -> collator.compare(Locale("", a.code).getDisplayCountry(locale), Locale("", b.code).getDisplayCountry(locale)) }
    LaunchedEffect(countries, state.loads[Area.COUNTRIES]?.phase) {
        if (state.loads[Area.COUNTRIES]?.phase == LoadPhase.READY && selected != "AUTO" && countries.none { it.code == selected }) selected = "AUTO"
    }
    PhoneScreen("live-account") {
        AccountSummary(state.data)
        OperationError(state.loads[Area.HOME]?.error)
        BrandCard {
            Text(tr(R.string.dash_where), style = MaterialTheme.typography.titleMedium)
            val selectedCountry = countries.find { it.code == selected }
            BoxWithConstraints {
                val menuWidth = maxWidth
                OutlinedButton({ expanded = true }, Modifier.fillMaxWidth().testTag("home-country")) {
                    LocationLabel(selectedCountry?.code, selectedCountry?.let { Locale("", it.code).getDisplayCountry(locale) } ?: tr(R.string.ui_autopilot),
                        selectedCountry?.quality?.toIntOrNull() ?: state.data.autopilotQuality, Modifier.weight(1f))
                    Text("⌄", Modifier.padding(start = 8.dp))
                }
                DropdownMenu(expanded, { expanded = false }, Modifier.width(menuWidth).heightIn(max = 360.dp)) {
                    DropdownMenuItem({ LocationLabel(null, tr(R.string.ui_autopilot), state.data.autopilotQuality) },
                        { selected = "AUTO"; expanded = false }, Modifier.testTag("home-country-AUTO"))
                    HorizontalDivider()
                    countries.sortedByDescending { it.quality.toIntOrNull() ?: 0 }.take(3).takeIf { it.isNotEmpty() }?.let { top ->
                        Text(tr(R.string.dash_top), Modifier.padding(12.dp), style = MaterialTheme.typography.bodySmall, color = Brand.Scorpion)
                        top.forEach { c -> DropdownMenuItem({ LocationLabel(c.code, Locale("", c.code).getDisplayCountry(locale), c.quality.toIntOrNull()) },
                            { selected = c.code; expanded = false }, Modifier.testTag("home-top-${c.code}")) }
                        HorizontalDivider()
                    }
                    Text(tr(R.string.dash_all_countries), Modifier.padding(12.dp), style = MaterialTheme.typography.bodySmall, color = Brand.Scorpion)
                    countries.forEach { c -> DropdownMenuItem({ LocationLabel(c.code, Locale("", c.code).getDisplayCountry(locale), c.quality.toIntOrNull()) },
                        { selected = c.code; expanded = false }, Modifier.testTag("home-country-${c.code}")) }
                    if (countries.isEmpty()) DropdownMenuItem({ Text(tr(R.string.dash_no_countries)) }, {}, enabled = false)
                }
            }
            if (state.loads[Area.COUNTRIES]?.phase == LoadPhase.LOADING) LinearProgressIndicator(Modifier.fillMaxWidth(), color = Brand.PurpleHeart)
            OperationError(state.loads[Area.COUNTRIES]?.error)
            BrandActionButton(tr(R.string.dash_connect), {}, Modifier.testTag("home-connect"))
            Text(tr(R.string.ui_not_connected), style = MaterialTheme.typography.titleMedium)
            Text(tr(R.string.dash_preview), style = MaterialTheme.typography.bodySmall, color = Brand.Scorpion)
            HorizontalDivider(color = Brand.DustyGray)
            Row(Modifier.fillMaxWidth().testTag("home-network"), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(countryFlag(location?.country), style = MaterialTheme.typography.bodyMedium)
                Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    val region = location?.let { value -> listOfNotNull(value.city, value.country?.let { Locale("", it).getDisplayCountry(locale) }).joinToString(", ") }?.takeIf { it.isNotBlank() }
                    Text(tr(R.string.dash_region) + ": " + (region ?: tr(R.string.unavailable)), style = MaterialTheme.typography.bodySmall, color = Brand.Scorpion)
                    Text("IP: " + (location?.ip ?: tr(R.string.unavailable)), style = MaterialTheme.typography.bodySmall, color = Brand.Scorpion)
                }
            }
        }
        BrandCard {
            Text(tr(R.string.ui_what_to_protect), style = MaterialTheme.typography.titleMedium)
            listOf(R.string.dash_all_traffic, R.string.dash_include, R.string.dash_exclude).forEachIndexed { index, title ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    RadioButton(index == 0, {}, enabled = index == 0)
                    Column(Modifier.weight(1f)) {
                        Text(tr(title), color = if (index == 0) Brand.Black else Brand.Scorpion)
                        if (index != 0) Text(tr(R.string.dash_soon), style = MaterialTheme.typography.bodySmall, color = Brand.Scorpion)
                    }
                }
            }
        }
    }
}

/** ISO flags use Android's emoji font, just as the language selector does. */
internal fun countryFlag(code: String?): String = if (code?.matches(Regex("[A-Z]{2}")) == true)
    code.map { String(Character.toChars(0x1F1E6 + it.code - 'A'.code)) }.joinToString("") else "🌐"

@Composable
private fun LocationLabel(code: String?, name: String, quality: Int?, modifier: Modifier = Modifier) {
    val qualityLabel = strings()(R.string.location_quality, quality?.toString() ?: "—")
    Row(modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(countryFlag(code), style = MaterialTheme.typography.bodyMedium)
        Text(name, Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
        // The server's availability score, not latency, speed or a fabricated measurement.
        Text(quality?.toString() ?: "—", Modifier.semantics { contentDescription = qualityLabel },
            style = MaterialTheme.typography.labelLarge, color = Brand.PurpleHeart)
    }
}
