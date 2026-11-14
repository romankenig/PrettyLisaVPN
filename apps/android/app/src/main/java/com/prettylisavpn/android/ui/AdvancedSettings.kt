package com.prettylisavpn.android.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material3.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import com.prettylisavpn.android.R
import com.prettylisavpn.android.vpn.MethodSelection
import com.prettylisavpn.android.vpn.connectionMethods

@Composable
internal fun AdvancedSettings(selection: MethodSelection, back: () -> Unit) {
    val tr = strings()
    val selected by selection.selected.collectAsState()
    val active = selected ?: connectionMethods.map { it.id }
    val displayed = connectionMethods.sortedBy { method -> active.indexOf(method.id).takeIf { it >= 0 } ?: (active.size + connectionMethods.indexOf(method)) }
    PhoneScreen("advanced-settings") {
        ScreenHeading(tr(R.string.advanced_settings), back)
        BrandCard {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(tr(R.string.connection_methods), Modifier.weight(1f), style = MaterialTheme.typography.titleLarge)
                IconButton({ selection.randomize() }, Modifier.size(48.dp).testTag("randomize-methods")) {
                    Icon(Icons.Outlined.Refresh, tr(R.string.randomize_methods), Modifier.size(18.dp), tint = Brand.Christalle.copy(alpha = .6f))
                }
            }
            Text(tr(R.string.connection_methods_hint), color = Brand.Scorpion)
            Text(tr(R.string.method_order_hint), style = MaterialTheme.typography.bodySmall, color = Brand.Scorpion)
            MethodCheckbox(tr(R.string.all_methods), selected == null, selected != null, "all-methods", selection::all)
            HorizontalDivider()
            displayed.chunked(2).forEach { pair -> Row(Modifier.fillMaxWidth()) {
                pair.forEach { method ->
                    MethodCheckbox(method.label, method.id in active, active.size > 1 || method.id !in active,
                        "method-${method.id}", { selection.toggle(method.id) }, Modifier.weight(1f))
                }
            } }
        }
    }
}

@Composable
private fun MethodCheckbox(label: String, checked: Boolean, enabled: Boolean, tag: String, change: () -> Unit, modifier: Modifier = Modifier) {
    Row(modifier.heightIn(min = 48.dp).testTag(tag).toggleable(value = checked, enabled = enabled, role = Role.Checkbox, onValueChange = { change() }),
        verticalAlignment = Alignment.CenterVertically) {
        Checkbox(checked = checked, onCheckedChange = null, enabled = enabled,
            colors = CheckboxDefaults.colors(checkedColor = Brand.PurpleHeart))
        Text(label, Modifier.padding(start = 8.dp), style = MaterialTheme.typography.bodyMedium)
    }
}
