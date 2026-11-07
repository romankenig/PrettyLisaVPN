package com.prettylisavpn.android.ui

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import com.prettylisavpn.android.R

/** Muted feature preview plus a separate readable, accessible registration action. */
@Composable
internal fun DemoLockedFeature(label: String, tag: String, register: () -> Unit) {
    Surface(onClick = register, modifier = Modifier.fillMaxWidth().testTag(tag), shape = MaterialTheme.shapes.medium,
        color = Brand.Christalle.copy(alpha = .06f), contentColor = Brand.Christalle) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(label, Modifier.alpha(.45f), style = MaterialTheme.typography.titleSmall)
            Text("🔒 " + strings()(R.string.demo_locked_hint), style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
internal fun DemoTraffic(register: () -> Unit) {
    val tr = strings()
    BrandCard(Modifier.testTag("demo-traffic")) {
        Text(tr(R.string.ui_what_to_protect), style = MaterialTheme.typography.titleMedium)
        Text("🛡️ " + tr(R.string.demo_full_traffic), color = Brand.Christalle)
        Text(tr(R.string.traffic_description_all), style = MaterialTheme.typography.bodySmall, color = Brand.Scorpion)
        DemoLockedFeature(tr(R.string.traffic_include_short), "demo-locked-include", register)
        DemoLockedFeature(tr(R.string.traffic_exclude_short), "demo-locked-exclude", register)
    }
}

@Composable
internal fun DemoUpgradeScreen(back: () -> Unit, register: () -> Unit) {
    val tr = strings()
    PhoneScreen("demo-upgrade-screen") {
        ScreenHeading(tr(R.string.ui_subscription), back)
        BrandCard {
            Text(planLabel("Demo"), style = MaterialTheme.typography.headlineMedium)
            Text(tr(R.string.demo_intro))
        }
        BrandCard {
            Text(planLabel("Free"), style = MaterialTheme.typography.headlineMedium)
            Text(tr(R.string.demo_upgrade_details))
            BrandActionButton(tr(R.string.demo_upgrade), register, Modifier.testTag("demo-register"))
        }
    }
}
