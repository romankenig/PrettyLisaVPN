package com.prettylisavpn.android.ui

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material3.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import com.prettylisavpn.android.R
import com.prettylisavpn.android.vpn.MethodSelection
import com.prettylisavpn.android.vpn.connectionMethods
import java.util.Locale

@Composable
internal fun AdvancedSettings(selection: MethodSelection, back: () -> Unit) {
    val tr = strings()
    val selected by selection.selected.collectAsState()
    val active = selected ?: connectionMethods.map { it.id }
    val displayed = remember { connectionMethods.sortedBy { it.label.lowercase(Locale.ROOT) } }
    var randomization by remember { mutableIntStateOf(0) }
    var highlighted by remember { mutableStateOf(emptySet<String>()) }
    val highlight = remember { Animatable(0f) }
    val rotation by animateFloatAsState(randomization.toFloat() * 360f, tween(400), label = "random-methods-rotation")
    LaunchedEffect(randomization) {
        if (randomization > 0) {
            highlight.snapTo(1f)
            highlight.animateTo(0f, tween(650))
        }
    }
    PhoneScreen("advanced-settings") {
        ScreenHeading(tr(R.string.advanced_settings), back)
        BrandCard {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(tr(R.string.connection_methods), Modifier.weight(1f), style = MaterialTheme.typography.titleLarge)
                IconButton({
                    val before = (selection.current() ?: connectionMethods.map { it.id }).toSet()
                    selection.randomize()
                    val after = requireNotNull(selection.current()).toSet()
                    // An order-only draw still acknowledges the affected selection.
                    highlighted = ((before - after) + (after - before)).ifEmpty { after }
                    randomization++
                }, Modifier.size(48.dp).testTag("randomize-methods")) {
                    Icon(Icons.Outlined.Refresh, tr(R.string.randomize_methods), Modifier.size(18.dp).rotate(rotation), tint = Brand.Christalle.copy(alpha = .6f))
                }
            }
            MethodCheckbox(tr(R.string.all_methods), selected == null, selected != null, "all-methods", {
                highlighted = emptySet()
                selection.all()
            })
            HorizontalDivider()
            displayed.chunked(2).forEach { pair -> Row(Modifier.fillMaxWidth()) {
                pair.forEach { method -> key(method.id) {
                    MethodCheckbox(method.label, method.id in active, active.size > 1 || method.id !in active,
                        "method-${method.id}", {
                            highlighted = emptySet()
                            selection.toggle(method.id)
                        }, Modifier.weight(1f).background(
                            Brand.Heliotrope.copy(alpha = if (method.id in highlighted) .28f * highlight.value else 0f),
                            MaterialTheme.shapes.small,
                        ))
                } }
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
