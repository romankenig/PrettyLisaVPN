package com.prettylisavpn.android.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.BasicText
import androidx.compose.foundation.text.TextAutoSize
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import com.prettylisavpn.android.R
import com.prettylisavpn.android.data.BillingOverview
import com.prettylisavpn.android.data.OfferPrice
import java.math.BigDecimal
import java.text.NumberFormat
import java.util.Locale

internal fun subscriptionMoney(amount: Long, currency: String, locale: Locale): String {
    val number = NumberFormat.getNumberInstance(locale).apply {
        minimumFractionDigits = if (amount % 100L == 0L) 0 else 2
        maximumFractionDigits = 2
    }.format(BigDecimal.valueOf(amount, 2))
    return when (currency) { "RUB" -> "$number ₽"; "USD" -> "$$number"; else -> "$number $currency" }
}

/** Parse the already validated API projection for presentation, never for a payment quote. */
internal fun subscriptionContractPrice(value: String?): Pair<String, OfferPrice>? = runCatching {
    val parts = value?.split(' ', limit = 2) ?: return@runCatching null
    if (parts.size != 2 || parts[0] !in setOf("RUB", "USD")) return@runCatching null
    val amount = parts[1].toBigDecimal().movePointRight(2).longValueExact()
    if (amount < 0) return@runCatching null
    parts[0] to OfferPrice(amount)
}.getOrNull()

internal fun subscriptionPurchaseRoutes(billing: BillingOverview, currency: String) =
    billing.routes.filter { route ->
        (billing.permits("SUBSCRIBE") || billing.permits("RENEW")) && currency in route.currencies
    }

@Composable
internal fun SubscriptionDetail(label: String, value: String, tag: String? = null) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp), modifier = if (tag == null) Modifier else Modifier.testTag(tag)) {
        Text(label, style = MaterialTheme.typography.bodySmall, color = Brand.Scorpion)
        Text(value, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
internal fun SubscriptionPriceCard(
    title: String,
    prices: Map<String, OfferPrice>,
    currency: String,
    locale: Locale,
    selectCurrency: ((String) -> Unit)?,
    enabled: Boolean,
    modifier: Modifier = Modifier,
    note: String? = null,
    featured: Boolean = false,
    current: Boolean = false,
    footer: (@Composable ColumnScope.() -> Unit)? = null,
) {
    val tr = strings()
    val foreground = if (featured) Brand.Mercury else Brand.Christalle
    val secondary = if (featured) Brand.Mercury.copy(alpha = .8f) else Brand.Scorpion
    Surface(modifier.fillMaxWidth(), shape = MaterialTheme.shapes.large,
        color = if (featured) Brand.Christalle else Brand.Mercury, contentColor = foreground,
        border = BorderStroke(1.dp, if (featured) Brand.Heliotrope.copy(alpha = .55f) else Brand.Heliotrope.copy(alpha = .2f))) {
      Column(Modifier.padding(if (featured) 24.dp else 20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        if (current) PlanCurrentBadge("PREMIUM", featured)
        Text(title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
        if (featured) Text(tr(R.string.plan_unlimited), style = MaterialTheme.typography.titleMedium, color = Brand.Viking)
        val price = prices[currency]
        if (price != null) BoxWithConstraints(Modifier.fillMaxWidth()) {
            val stacked = maxWidth < 260.dp || LocalDensity.current.fontScale > 1.3f
            val amount: @Composable () -> Unit = {
                Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    price.original?.takeIf { it > price.amount }?.let {
                        Text(subscriptionMoney(it, currency, locale), color = secondary,
                            textDecoration = TextDecoration.LineThrough, style = MaterialTheme.typography.titleMedium,
                            modifier = Modifier.testTag("billing-original-price"))
                    }
                    BasicText(subscriptionMoney(price.amount, currency, locale),
                        style = MaterialTheme.typography.displayMedium.copy(color = foreground,
                            fontSize = 48.sp, lineHeight = 1.125.em, fontWeight = FontWeight.Bold),
                        autoSize = TextAutoSize.StepBased(minFontSize = 32.sp, maxFontSize = 48.sp, stepSize = 1.sp),
                        maxLines = 1, modifier = Modifier.testTag("billing-price"))
                    Text(tr(R.string.subscription_per_month), color = secondary, style = MaterialTheme.typography.bodyMedium)
                }
            }
            val currencies: @Composable () -> Unit = {
                if (selectCurrency != null) Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    listOf("RUB", "USD").filter { it in prices }.forEach { code ->
                        Surface(onClick = { selectCurrency(code) }, enabled = enabled, selected = currency == code,
                            modifier = Modifier.widthIn(min = 68.dp).heightIn(min = 48.dp).testTag("billing-currency-$code"),
                            shape = MaterialTheme.shapes.small,
                            color = if (currency == code) (if (featured) Brand.Viking else Brand.Christalle) else Brand.Heliotrope.copy(alpha = 0.14f),
                            contentColor = if (featured) (if (currency == code) Brand.Christalle else Brand.Mercury) else (if (currency == code) Brand.Mercury else Brand.Christalle),
                            border = BorderStroke(1.dp, (if (featured) Brand.Heliotrope else Brand.Christalle).copy(alpha = .4f))) {
                            Box(Modifier.padding(horizontal = 12.dp, vertical = 8.dp), contentAlignment = Alignment.Center) {
                                Text(code, style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold)
                            }
                        }
                    }
                }
            }
            if (stacked) Column(verticalArrangement = Arrangement.spacedBy(12.dp)) { amount(); currencies() }
            else Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.weight(1f)) { amount() }
                currencies()
            }
        }
        if (featured) PlanHighlights("PREMIUM", featured = true)
        note?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = secondary) }
        footer?.invoke(this)
      }
    }
}

@Composable
internal fun SubscriptionManageButton(label: String, onClick: () -> Unit, tag: String, enabled: Boolean, danger: Boolean = false) {
    val color = if (danger) Brand.PersianRed else Brand.Christalle
    OutlinedButton(onClick, modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp).testTag(tag), enabled = enabled,
        shape = MaterialTheme.shapes.medium, contentPadding = PaddingValues(14.dp),
        border = BorderStroke(1.dp, if (enabled) color else Brand.DustyGray),
        colors = ButtonDefaults.outlinedButtonColors(contentColor = color, disabledContentColor = Brand.Scorpion)) {
        Text(label, style = if (danger) MaterialTheme.typography.titleMedium.copy(fontSize = 20.sp, fontWeight = FontWeight.Bold) else MaterialTheme.typography.labelLarge)
    }
}
