package com.prettylisavpn.android.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import com.prettylisavpn.android.R
import com.prettylisavpn.android.data.*
import com.prettylisavpn.android.vpn.*
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeout

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
                model.vpn?.let { vpn ->
                    if (vpn.status.value.phase != VpnPhase.DISCONNECTED) {
                        vpn.disconnect()
                        val stopped = withTimeout(45_000) { vpn.status.first { it.phase == VpnPhase.DISCONNECTED || it.phase == VpnPhase.FAILED } }
                        check(stopped.phase == VpnPhase.DISCONNECTED)
                    }
                }
                store.save(next); opened = false
            } catch (_: TimeoutCancellationException) { failed = true }
            catch (e: CancellationException) { throw e }
            catch (_: Exception) { failed = true }
            finally { busy = false }
        }
    }
    BrandCard {
        Text(tr(R.string.ui_what_to_protect), style = MaterialTheme.typography.titleMedium)
        listOf("all" to R.string.dash_all_traffic, "include" to R.string.dash_include, "exclude" to R.string.dash_exclude).forEach { (mode, label) ->
            Row(verticalAlignment = Alignment.CenterVertically) {
                RadioButton(selected.mode == mode, { save(selected.copy(mode = mode)) }, enabled = !busy, modifier = Modifier.testTag("traffic-mode-$mode"))
                Text(tr(label), Modifier.weight(1f))
            }
        }
        BrandActionButton(tr(R.string.traffic_services), { opened = true; model.load(Area.TRAFFIC) }, Modifier.testTag("traffic-services"), enabled = !busy)
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
            if (state.loads[Area.TRAFFIC]?.phase == LoadPhase.LOADING) LinearProgressIndicator(Modifier.fillMaxWidth())
            if (state.loads[Area.TRAFFIC]?.phase == LoadPhase.ERROR) {
                Text(tr(R.string.traffic_catalog_unavailable))
                TextButton({ model.load(Area.TRAFFIC) }) { Text(tr(R.string.ui_retry)) }
            }
            services.forEach { service ->
                val checked = list.services.any { it.id == service.id }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(checked, { update(list.copy(services = if (checked) list.services.filter { it.id != service.id } else list.services + service)) }, enabled = !busy,
                        modifier = Modifier.testTag("traffic-service-${service.slug}"))
                    ServiceIcon(service.icon)
                    Text(service.name, Modifier.padding(start = 8.dp), style = MaterialTheme.typography.titleSmall)
                }
                Text(service.domains.joinToString(", "), style = MaterialTheme.typography.bodySmall, color = Brand.Scorpion)
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
        dismissButton = { TextButton(close, enabled = !busy) { Text(tr(R.string.traffic_cancel)) } })
}

@Composable
private fun ServiceIcon(icon: String) {
    Canvas(Modifier.size(26.dp)) {
        val color = Brand.PurpleHeart
        val unit = size.width / 24
        if (icon == "youtube") {
            drawRoundRect(color, Offset(2*unit, 5*unit), Size(20*unit, 14*unit), CornerRadius(4*unit), style = Stroke(1.7f*unit))
            drawPath(Path().apply { moveTo(10*unit, 9*unit); lineTo(16*unit, 12*unit); lineTo(10*unit, 15*unit); close() }, color)
        } else {
            drawRoundRect(color, Offset(3*unit, 3*unit), Size(18*unit, 18*unit), CornerRadius(5*unit), style = Stroke(1.7f*unit))
            drawCircle(color, 4*unit, Offset(12*unit, 12*unit), style = Stroke(1.7f*unit))
            drawCircle(color, unit, Offset(17.5f*unit, 6.5f*unit))
        }
    }
}
