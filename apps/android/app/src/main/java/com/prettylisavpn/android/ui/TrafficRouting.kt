package com.prettylisavpn.android.ui

import androidx.compose.foundation.Canvas
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.Dp
import com.prettylisavpn.android.R
import com.prettylisavpn.android.data.*
import com.prettylisavpn.android.vpn.*
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.launch
import kotlinx.coroutines.delay

@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun TrafficRouting(model: ScreenModel, refreshKey: Int = 0) {
    val tr = strings()
    val context = LocalContext.current
    val store = remember { DeviceTrafficSelection.get(context) }
    val selected by store.selected.collectAsState()
    val presentation = LocalPresentation.current
    val vpn by (model.vpn?.status ?: remember { kotlinx.coroutines.flow.MutableStateFlow(VpnStatus()) }).collectAsState()
    var vpnLocation by remember { mutableStateOf<PublicLocation?>(null) }
    var locating by remember { mutableStateOf(false) }
    LaunchedEffect(presentation, selected.mode, vpn.phase, vpn.method, refreshKey) {
        vpnLocation = null; locating = false
        if (selected.mode != "all" && vpn.phase == VpnPhase.CONNECTED) {
            while (true) {
                locating = true
                vpnLocation = if (selected.mode == "exclude") presentation.directLocation() else presentation.vpnLocation()
                locating = false
                delay(60_000)
            }
        }
    }
    var opened by remember { mutableStateOf(false) }
    var modeMenu by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var failed by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    fun save(next: TrafficSelection) {
        if (busy) return
        busy = true; failed = false
        scope.launch {
            try {
                applyTrafficSelection(next, store, model.vpn)
                opened = false
            } catch (_: TimeoutCancellationException) { failed = true }
            catch (e: CancellationException) { throw e }
            catch (_: Exception) { failed = true }
            finally { busy = false }
        }
    }
    BrandCard {
        FlowRow(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(tr(R.string.ui_what_to_protect), Modifier.align(Alignment.CenterVertically), style = MaterialTheme.typography.titleMedium)
            Box(Modifier.widthIn(max = 240.dp).align(Alignment.CenterVertically)) {
                val options = listOf("all" to R.string.traffic_all_short, "include" to R.string.traffic_include_short, "exclude" to R.string.traffic_exclude_short)
                TextButton({ modeMenu = true }, enabled = !busy, contentPadding = PaddingValues(horizontal = 10.dp), modifier = Modifier.testTag("traffic-mode-menu")) {
                    Text(tr(options.first { it.first == selected.mode }.second), Modifier.weight(1f, fill = false), style = MaterialTheme.typography.titleMedium)
                    Text("⌄", Modifier.padding(start = 6.dp))
                }
                DropdownMenu(modeMenu, { modeMenu = false }) {
                    options.forEach { (mode, label) ->
                        DropdownMenuItem(text = { Text(tr(label)) }, enabled = !busy,
                            onClick = { modeMenu = false; if (selected.mode != mode) save(selected.copy(mode = mode)) },
                            modifier = Modifier.testTag("traffic-mode-$mode"))
                    }
                }
            }
        }
        if (selected.mode == "all") Text(tr(R.string.traffic_description_all),
            modifier = Modifier.testTag("traffic-mode-description"), style = MaterialTheme.typography.bodySmall, color = Brand.Scorpion.copy(alpha = 0.65f))
        if (selected.mode != "all") {
            Button({ opened = true; model.load(Area.TRAFFIC) }, Modifier.fillMaxWidth().testTag("traffic-services"), enabled = !busy,
                colors = ButtonDefaults.buttonColors(containerColor = Brand.Viking, contentColor = Brand.Black), shape = MaterialTheme.shapes.medium) { Text(tr(R.string.traffic_services)) }
            Text(tr(R.string.traffic_selected_label), style = MaterialTheme.typography.bodyMedium)
            val list = if (selected.mode == "include") selected.include else selected.exclude
            val selectionLabel = tr(R.string.traffic_selected)
            val items = list.services.map { it.name to it.icon } + list.masks.map { it to "website" }
            BoxWithConstraints(Modifier.fillMaxWidth().semantics { contentDescription = selectionLabel }.testTag("traffic-selected-strip")) {
                val slots = ((maxWidth.value + 4) / 24).toInt().coerceAtLeast(1)
                val logos = items.indices.filter { serviceDrawable(items[it].second) != null }
                val needsMore = logos.size < items.size || logos.size > slots
                val visible = logos.take((slots - if (needsMore) 1 else 0).coerceAtLeast(0))
                val hidden = items.filterIndexed { index, _ -> index !in visible }.joinToString(", ") { it.first }
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically) {
                    visible.forEach { index -> val (name, icon) = items[index]; Box(Modifier.semantics { contentDescription = name }) { ServiceIcon(icon, brand = true, iconSize = 20.dp) } }
                    if (hidden.isNotEmpty()) {
                        Canvas(Modifier.size(20.dp).semantics { contentDescription = hidden }.testTag("traffic-selected-more")) {
                            for (fraction in listOf(0.25f, 0.5f, 0.75f)) drawCircle(Brand.Scorpion, size.width / 16, Offset(size.width * fraction, size.height / 2))
                        }
                    }
                }
            }
        }
        if (failed) Text(tr(R.string.traffic_save_failed), color = Brand.PersianRed)
        if (selected.mode != "all") {
            HorizontalDivider(color = Brand.DustyGray)
            Column(Modifier.fillMaxWidth().testTag("vpn-location"), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                Text(tr(if (selected.mode == "exclude") R.string.direct_location else R.string.vpn_location), style = MaterialTheme.typography.labelMedium, color = Brand.Scorpion)
                if (locating) CircularProgressIndicator(Modifier.size(20.dp).testTag("vpn-location-loading"), strokeWidth = 2.dp)
                val value = vpnLocation
                if (vpn.phase != VpnPhase.CONNECTED) Text(tr(R.string.ui_not_connected), style = MaterialTheme.typography.bodySmall)
                else if (value == null) Text(tr(if (locating) R.string.vpn_location_loading else R.string.unavailable), style = MaterialTheme.typography.bodySmall)
                else {
                    val language by presentation.preference.language.collectAsState()
                    val locale = java.util.Locale.forLanguageTag(language.code)
                    val region = listOfNotNull(value.city, value.country?.let { java.util.Locale("", it).getDisplayCountry(locale) }).joinToString(", ")
                    Text(countryFlag(value.country) + " " + region.ifBlank { tr(R.string.unavailable) }, style = MaterialTheme.typography.bodySmall)
                    Text("IP: " + value.ip, style = MaterialTheme.typography.bodySmall, color = Brand.Scorpion)
                }
            }
        }
    }
    if (opened) TrafficDialog(model, selected, busy, failed, { opened = false }, ::save)
}

@Composable
private fun TrafficDialog(model: ScreenModel, initial: TrafficSelection, busy: Boolean, failed: Boolean, close: () -> Unit, save: (TrafficSelection) -> Unit) {
    val tr = strings()
    val language by LocalPresentation.current.preference.language.collectAsState()
    val state by model.state.collectAsState()
    var draft by remember { mutableStateOf(initial) }
    val tab by remember { mutableStateOf(if (initial.mode == "exclude") "exclude" else "include") }
    var query by remember { mutableStateOf("") }
    var input by remember { mutableStateOf("") }
    var invalid by remember { mutableStateOf(false) }
    var adding by remember { mutableStateOf(false) }
    val list = if (tab == "include") draft.include else draft.exclude
    fun update(value: TrafficList) { draft = if (tab == "include") draft.copy(include = value) else draft.copy(exclude = value) }
    val catalog = state.data.trafficServices
    val services = catalog + list.services.filter { saved -> catalog.none { it.id == saved.id } }
    AlertDialog(onDismissRequest = { if (!busy) close() }, title = { Text(tr(R.string.traffic_services)) },
        modifier = Modifier.testTag("traffic-dialog"),
        text = { Column(Modifier.heightIn(max = 460.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (state.loads[Area.TRAFFIC]?.phase == LoadPhase.LOADING) {
                Text(tr(R.string.traffic_loading))
                LinearProgressIndicator(Modifier.fillMaxWidth())
            }
            if (state.loads[Area.TRAFFIC]?.phase == LoadPhase.ERROR) {
                Text(tr(R.string.traffic_catalog_unavailable))
                TextButton({ model.load(Area.TRAFFIC) }) { Text(tr(R.string.ui_retry)) }
            }
            OutlinedTextField(query, { query = it }, singleLine = true, label = { Text(tr(R.string.traffic_search)) }, modifier = Modifier.fillMaxWidth().testTag("traffic-search"))
            Button({ adding = !adding; input = ""; invalid = false }, enabled = !busy,
                colors = ButtonDefaults.buttonColors(containerColor = Brand.Viking, contentColor = Brand.Black),
                modifier = Modifier.fillMaxWidth().testTag("traffic-add-service")) { Text("＋ " + tr(R.string.traffic_add_service)) }
            if (adding) {
            OutlinedTextField(input, { input = it }, enabled = !busy, label = { Text(tr(R.string.traffic_mask)) },
                placeholder = { Text("example.com, *.example.com") }, modifier = Modifier.fillMaxWidth().testTag("traffic-mask"))
            TextButton({
                try {
                    val masks = input.split(',', '\n').map(::normalizeTrafficMask)
                    require(list.masks.size + masks.size <= 256)
                    update(list.copy(masks = (list.masks + masks).distinct())); input = ""; invalid = false; adding = false
                } catch (_: Exception) { invalid = true }
            }, enabled = !busy && input.isNotBlank()) { Text(tr(R.string.traffic_add)) }
            if (invalid) Text(tr(R.string.traffic_mask_invalid), color = Brand.PersianRed)
            }
            list.masks.forEach { mask -> Row(verticalAlignment = Alignment.CenterVertically) {
                Text(mask, Modifier.weight(1f))
                TextButton({ update(list.copy(masks = list.masks - mask)) }, enabled = !busy) { Text(tr(R.string.traffic_remove)) }
            } }
            serviceGroups(services, tab, java.util.Locale.forLanguageTag(language.code), (if (tab == "include") initial.include else initial.exclude).services.map { it.id }.toSet()).forEach { (group, entries) ->
                Text(tr(if (group == "top") R.string.traffic_top else R.string.traffic_all_services), style = MaterialTheme.typography.titleSmall, color = Brand.Scorpion)
                entries.filter { it.name.contains(query.trim(), ignoreCase = true) }.forEach { service ->
                    val checked = list.services.any { it.id == service.id }
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        ServiceIcon(service.icon, brand = true)
                        Text(service.name, Modifier.weight(1f), style = MaterialTheme.typography.bodyLarge)
                        Switch(checked, { update(list.copy(services = if (checked) list.services.filter { it.id != service.id } else list.services + service)) }, enabled = !busy,
                            modifier = Modifier.testTag(if (group == "all") "traffic-service-${service.slug}" else "traffic-top-service-${service.slug}").semantics { contentDescription = service.name })
                    }
                }
            }
            if (failed) Text(tr(R.string.traffic_save_failed), color = Brand.PersianRed)
        } },
        confirmButton = { TextButton({ save(draft.refreshServices(catalog)) }, enabled = !busy && input.isBlank(), modifier = Modifier.testTag("traffic-save")) { Text(tr(R.string.traffic_save)) } },
        dismissButton = { TextButton(close, enabled = !busy) { Text(tr(R.string.ui_cancel)) } })
}

private fun serviceDrawable(icon: String): Int? = when(icon) {
        "anthropic" -> R.drawable.service_anthropic
        "spotify" -> R.drawable.service_spotify
        "netflix" -> R.drawable.service_netflix
        "twitch" -> R.drawable.service_twitch
        "reddit" -> R.drawable.service_reddit
        "pinterest" -> R.drawable.service_pinterest
        "snapchat" -> R.drawable.service_snapchat
        "threads" -> R.drawable.service_threads
        "viber" -> R.drawable.service_viber
        "zoom" -> R.drawable.service_zoom
        "steam" -> R.drawable.service_steam
        "epicgames" -> R.drawable.service_epicgames
        "playstation" -> R.drawable.service_playstation
        "roblox" -> R.drawable.service_roblox
        "google" -> R.drawable.service_google
        "google-play" -> R.drawable.service_google_play
        "apple-music" -> R.drawable.service_apple_music
        "youtube-music" -> R.drawable.service_youtube_music
        "deezer" -> R.drawable.service_deezer
        "soundcloud" -> R.drawable.service_soundcloud
        "tidal" -> R.drawable.service_tidal
        "hbo" -> R.drawable.service_hbo
        "notion" -> R.drawable.service_notion
        "trello" -> R.drawable.service_trello
        "deepseek" -> R.drawable.service_deepseek
        "gemini" -> R.drawable.service_gemini
        "ebay" -> R.drawable.service_ebay
        "airbnb" -> R.drawable.service_airbnb
        "booking" -> R.drawable.service_booking
        "patreon" -> R.drawable.service_patreon
        "youtube" -> R.drawable.service_youtube
        "instagram" -> R.drawable.service_instagram
        "facebook" -> R.drawable.service_facebook
        "whatsapp" -> R.drawable.service_whatsapp
        "telegram" -> R.drawable.service_telegram
        "discord" -> R.drawable.service_discord
        "signal" -> R.drawable.service_signal
        "x" -> R.drawable.service_x
        "tiktok" -> R.drawable.service_tiktok
        "vk" -> R.drawable.service_vk
        "ok" -> R.drawable.service_ok
        "mail" -> R.drawable.service_mail
        else -> null
}

@Composable
private fun ServiceIcon(icon: String, brand: Boolean = false, iconSize: Dp = 26.dp) {
    val color = if (brand) serviceColor(icon) else Brand.PurpleHeart
    val drawable = serviceDrawable(icon)
    if (drawable != null) {
        Icon(androidx.compose.ui.res.painterResource(drawable), contentDescription = null, tint = color, modifier = Modifier.size(iconSize))
        return
    }
    val badge = mapOf("linkedin" to "in", "max" to "M", "yandex" to "Я", "ozon" to "O", "wildberries" to "WB", "gosuslugi" to "ГУ", "rutube" to "R", "dzen" to "Д")[icon]
    if (badge != null) {
        Surface(color = color, contentColor = Color.White, shape = MaterialTheme.shapes.small) {
            Box(Modifier.size(iconSize), contentAlignment = Alignment.Center) { Text(badge, style = MaterialTheme.typography.labelSmall, fontSize = if (brand) with(LocalDensity.current) { 9.dp.toSp() } else MaterialTheme.typography.labelSmall.fontSize, maxLines = 1) }
        }
        return
    }
    Canvas(Modifier.size(iconSize)) {
        val unit = size.width / 24
        drawCircle(color, 10*unit, style = Stroke(1.7f*unit))
        drawOval(color, Offset(7*unit, 2*unit), Size(10*unit, 20*unit), style = Stroke(1.7f*unit))
        drawLine(color, Offset(2*unit, 12*unit), Offset(22*unit, 12*unit), 1.7f*unit)
    }
}

/** Service identity colors on Home and in the picker. */
private fun serviceColor(icon: String): Color = Color(when(icon) {
    "anthropic" -> 0xFF191919
    "spotify" -> 0xFF1ED760
    "netflix" -> 0xFFE50914
    "twitch" -> 0xFF9146FF
    "reddit" -> 0xFFFF4500
    "pinterest" -> 0xFFBD081C
    "snapchat" -> 0xFFFFFC00
    "threads" -> 0xFF000000
    "viber" -> 0xFF7360F2
    "zoom" -> 0xFF0B5CFF
    "steam" -> 0xFF000000
    "epicgames" -> 0xFF313131
    "playstation" -> 0xFF0070D1
    "roblox" -> 0xFF000000
    "google" -> 0xFF4285F4
    "google-play" -> 0xFF414141
    "apple-music" -> 0xFFFA243C
    "youtube-music" -> 0xFFFF0000
    "deezer" -> 0xFFA238FF
    "soundcloud" -> 0xFFFF5500
    "tidal" -> 0xFF000000
    "hbo" -> 0xFF000000
    "notion" -> 0xFF000000
    "trello" -> 0xFF0052CC
    "deepseek" -> 0xFF5786FE
    "gemini" -> 0xFF8E75B2
    "ebay" -> 0xFFE53238
    "airbnb" -> 0xFFFF5A5F
    "booking" -> 0xFF003A9A
    "patreon" -> 0xFF000000
    "youtube" -> 0xFFFF0000; "instagram" -> 0xFFFF0069; "facebook" -> 0xFF0866FF
    "whatsapp" -> 0xFF25D366; "telegram" -> 0xFF26A5E4; "discord" -> 0xFF5865F2
    "signal" -> 0xFF3B45FD; "x", "tiktok" -> 0xFF000000; "linkedin" -> 0xFF0A66C2
    "vk" -> 0xFF0077FF; "ok" -> 0xFFEE8208; "mail" -> 0xFF005FF9; "max" -> 0xFF5B51D8
    "yandex" -> 0xFFFC3F1D; "ozon" -> 0xFF005BFF; "wildberries" -> 0xFFCB11AB
    "gosuslugi" -> 0xFF0D4CD3; "rutube" -> 0xFF100943; "dzen" -> 0xFF2C3036
    else -> 0xFF5B5B5B
})
