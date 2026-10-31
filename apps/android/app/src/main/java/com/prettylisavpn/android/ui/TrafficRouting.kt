package com.prettylisavpn.android.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.ui.semantics.Role
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import com.prettylisavpn.android.R
import com.prettylisavpn.android.data.*
import com.prettylisavpn.android.vpn.*
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.launch

@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun TrafficRouting(model: ScreenModel) {
    val tr = strings()
    val context = LocalContext.current
    val store = remember { DeviceTrafficSelection.get(context) }
    val selected by store.selected.collectAsState()
    var opened by remember { mutableStateOf(false) }
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
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(tr(R.string.ui_what_to_protect), Modifier.weight(1f), style = MaterialTheme.typography.titleMedium)
            TextButton({ opened = true; model.load(Area.TRAFFIC) }, Modifier.testTag("traffic-services"), enabled = !busy) { Text(tr(R.string.traffic_services)) }
        }
        FlowRow(Modifier.fillMaxWidth().selectableGroup(), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            listOf("all" to R.string.traffic_all_short, "include" to R.string.traffic_include_short, "exclude" to R.string.traffic_exclude_short).forEach { (mode, label) ->
                Surface(shape = MaterialTheme.shapes.large, color = if (selected.mode == mode) Brand.PurpleHeart else Brand.Mercury,
                    contentColor = if (selected.mode == mode) androidx.compose.ui.graphics.Color.White else Brand.Scorpion,
                    modifier = Modifier.selectable(selected.mode == mode, enabled = !busy, role = Role.RadioButton) { save(selected.copy(mode = mode)) }.testTag("traffic-mode-$mode")) {
                    Text(tr(label), Modifier.padding(horizontal = 14.dp, vertical = 12.dp), style = MaterialTheme.typography.labelLarge)
                }
            }
        }
        Text(tr(when(selected.mode) { "include" -> R.string.dash_include; "exclude" -> R.string.dash_exclude; else -> R.string.dash_all_traffic }), style = MaterialTheme.typography.bodySmall, color = Brand.Scorpion)
        if (selected.mode != "all") {
            val list = if (selected.mode == "include") selected.include else selected.exclude
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                list.services.forEach { service -> Box(Modifier.semantics { contentDescription = service.name }.padding(4.dp)) { ServiceIcon(service.icon) } }
                list.masks.forEach { mask -> Box(Modifier.semantics { contentDescription = mask }.padding(4.dp)) { ServiceIcon("website") } }
            }
        }
        if (failed) Text(tr(R.string.traffic_save_failed), color = Brand.PersianRed)
    }
    if (opened) TrafficDialog(model, selected, busy, failed, { opened = false }, ::save)
}

@Composable
private fun TrafficDialog(model: ScreenModel, initial: TrafficSelection, busy: Boolean, failed: Boolean, close: () -> Unit, save: (TrafficSelection) -> Unit) {
    val tr = strings()
    val state by model.state.collectAsState()
    var draft by remember { mutableStateOf(initial) }
    var tab by remember { mutableStateOf(if (initial.mode == "exclude") "exclude" else "include") }
    var query by remember { mutableStateOf("") }
    var input by remember { mutableStateOf("") }
    var invalid by remember { mutableStateOf(false) }
    val list = if (tab == "include") draft.include else draft.exclude
    fun update(value: TrafficList) { draft = if (tab == "include") draft.copy(include = value) else draft.copy(exclude = value) }
    val catalog = state.data.trafficServices
    val services = catalog + list.services.filter { saved -> catalog.none { it.id == saved.id } }
    AlertDialog(onDismissRequest = { if (!busy) close() }, title = { Text(tr(R.string.traffic_services)) },
        modifier = Modifier.testTag("traffic-dialog"),
        text = { Column(Modifier.heightIn(max = 460.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(tr(R.string.traffic_save_hint))
            listOf("include" to R.string.dash_include, "exclude" to R.string.dash_exclude).forEach { (mode, label) ->
                OutlinedButton({ tab = mode; input = ""; invalid = false }, enabled = !busy, modifier = Modifier.fillMaxWidth().testTag("traffic-tab-$mode")) {
                    Text((if (tab == mode) "✓ " else "") + tr(label))
                }
            }
            if (state.loads[Area.TRAFFIC]?.phase == LoadPhase.LOADING) {
                Text(tr(R.string.traffic_loading))
                LinearProgressIndicator(Modifier.fillMaxWidth())
            }
            if (state.loads[Area.TRAFFIC]?.phase == LoadPhase.ERROR) {
                Text(tr(R.string.traffic_catalog_unavailable))
                TextButton({ model.load(Area.TRAFFIC) }) { Text(tr(R.string.ui_retry)) }
            }
            OutlinedTextField(query, { query = it }, singleLine = true, label = { Text(tr(R.string.traffic_search)) }, modifier = Modifier.fillMaxWidth().testTag("traffic-search"))
            listOf("popular" to R.string.traffic_popular, "whitelist" to R.string.traffic_whitelist).forEach { (category, label) ->
                Text(tr(label), style = MaterialTheme.typography.titleSmall, color = Brand.Scorpion)
                services.filter { (it.category ?: "popular") == category && it.name.contains(query.trim(), ignoreCase = true) }.forEach { service ->
                    val checked = list.services.any { it.id == service.id }
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        ServiceIcon(service.icon)
                        Text(service.name, Modifier.weight(1f), style = MaterialTheme.typography.bodyLarge)
                        Switch(checked, { update(list.copy(services = if (checked) list.services.filter { it.id != service.id } else list.services + service)) }, enabled = !busy,
                            modifier = Modifier.testTag("traffic-service-${service.slug}").semantics { contentDescription = service.name })
                    }
                }
            }
            OutlinedTextField(input, { input = it }, enabled = !busy, label = { Text(tr(R.string.traffic_mask)) },
                placeholder = { Text("youtube.com, *.youtube.com") }, modifier = Modifier.fillMaxWidth().testTag("traffic-mask"))
            TextButton({
                try {
                    val masks = input.split(',', '\n').map(::normalizeTrafficMask)
                    require(list.masks.size + masks.size <= 256)
                    update(list.copy(masks = (list.masks + masks).distinct())); input = ""; invalid = false
                } catch (_: Exception) { invalid = true }
            }, enabled = !busy && input.isNotBlank()) { Text(tr(R.string.traffic_add)) }
            if (invalid) Text(tr(R.string.traffic_mask_invalid), color = Brand.PersianRed)
            list.masks.forEach { mask -> Row(verticalAlignment = Alignment.CenterVertically) {
                Text(mask, Modifier.weight(1f))
                TextButton({ update(list.copy(masks = list.masks - mask)) }, enabled = !busy) { Text(tr(R.string.traffic_remove)) }
            } }
            if (failed) Text(tr(R.string.traffic_save_failed), color = Brand.PersianRed)
        } },
        confirmButton = { TextButton({ save(draft.refreshServices(catalog)) }, enabled = !busy && input.isBlank(), modifier = Modifier.testTag("traffic-save")) { Text(tr(R.string.traffic_save)) } },
        dismissButton = { TextButton(close, enabled = !busy) { Text(tr(R.string.ui_cancel)) } })
}

@Composable
private fun ServiceIcon(icon: String) {
    val drawable = when(icon) {
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
    if (drawable != null) {
        Icon(androidx.compose.ui.res.painterResource(drawable), contentDescription = null, tint = Brand.PurpleHeart, modifier = Modifier.size(26.dp))
        return
    }
    val badge = mapOf("linkedin" to "in", "max" to "M", "yandex" to "Я", "ozon" to "O", "wildberries" to "WB", "gosuslugi" to "ГУ", "rutube" to "R", "dzen" to "Д")[icon]
    if (badge != null) {
        Surface(color = Brand.PurpleHeart, contentColor = androidx.compose.ui.graphics.Color.White, shape = MaterialTheme.shapes.small) {
            Box(Modifier.size(26.dp), contentAlignment = Alignment.Center) { Text(badge, style = MaterialTheme.typography.labelSmall) }
        }
        return
    }
    Canvas(Modifier.size(26.dp)) {
        val color = Brand.PurpleHeart
        val unit = size.width / 24
            drawCircle(color, 10*unit, style = Stroke(1.7f*unit))
            drawOval(color, Offset(7*unit, 2*unit), Size(10*unit, 20*unit), style = Stroke(1.7f*unit))
            drawLine(color, Offset(2*unit, 12*unit), Offset(22*unit, 12*unit), 1.7f*unit)
    }
}
