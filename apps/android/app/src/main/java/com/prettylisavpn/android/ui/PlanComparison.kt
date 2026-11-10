package com.prettylisavpn.android.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.prettylisavpn.android.R

@Composable
internal fun PlanCurrentBadge(plan: String, featured: Boolean = false) {
    Surface(color = if (featured) Brand.Viking else Brand.Christalle.copy(alpha = .08f),
        contentColor = Brand.Christalle, shape = MaterialTheme.shapes.small,
        modifier = Modifier.testTag("current-plan-$plan")) {
        Text(strings()(R.string.plan_current), Modifier.padding(horizontal = 10.dp, vertical = 5.dp),
            style = MaterialTheme.typography.labelMedium)
    }
}

@Composable
internal fun PlanHighlights(plan: String, featured: Boolean = false) {
    val tr = strings()
    val rows = when (plan) {
        "PREMIUM" -> listOf(R.string.plan_all_countries, R.string.plan_five_devices, R.string.plan_split)
        "FREE" -> listOf(R.string.plan_free_countries, R.string.plan_split)
        else -> listOf(R.string.plan_auto_only, R.string.plan_device_only, R.string.plan_all_traffic_only)
    }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        rows.forEach { label -> Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.Top) {
            Text(if (plan == "DEMO") "•" else "✓", color = if (featured) Brand.Viking else Brand.PurpleHeart)
            Text(tr(label), style = MaterialTheme.typography.bodyMedium,
                color = if (featured) Brand.Mercury else Brand.Scorpion, modifier = Modifier.weight(1f))
        } }
    }
}

/** Lower tiers are quieter, but their limits and the current tier stay explicit. */
@Composable
internal fun PlanTierCard(plan: String, current: Boolean, register: (() -> Unit)? = null, enabled: Boolean = true) {
    val tr = strings()
    Surface(Modifier.fillMaxWidth().testTag("plan-tier-$plan"), shape = MaterialTheme.shapes.large,
        color = if (plan == "DEMO") Brand.Mercury.copy(alpha = .9f) else Brand.Mercury,
        contentColor = Brand.Christalle,
        border = BorderStroke(if (current) 2.dp else 1.dp, if (current) Brand.Viking else Brand.Heliotrope.copy(alpha = .2f))) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            if (current) PlanCurrentBadge(plan)
            Text(planLabel(plan), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            Surface(color = Brand.PurpleHeart.copy(alpha = .08f), shape = MaterialTheme.shapes.small) {
                Text(tr(if (plan == "FREE") R.string.plan_registration_required else R.string.plan_no_registration),
                    Modifier.padding(horizontal = 10.dp, vertical = 6.dp).testTag("plan-registration-$plan"),
                    style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.SemiBold, color = Brand.Christalle)
            }
            Text(tr(if (plan == "FREE") R.string.plan_hour else R.string.plan_quarter_hour),
                style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            PlanHighlights(plan)
            if (plan == "FREE" && register != null) {
                Text(tr(R.string.plan_fresh_hour), style = MaterialTheme.typography.bodySmall, color = Brand.Scorpion)
                SubscriptionManageButton(tr(R.string.plan_register), register, "demo-register", enabled)
            }
        }
    }
}
