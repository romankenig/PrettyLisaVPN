package com.prettylisavpn.android.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.WindowInsetsSides
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.only
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.sizeIn
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.Check
import androidx.compose.material.icons.outlined.Home
import androidx.compose.material.icons.outlined.Info
import androidx.compose.material.icons.outlined.LocationOn
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.disabled
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.prettylisavpn.android.BuildConfig
import com.prettylisavpn.android.R

internal enum class Destination(val label: Int, val icon: ImageVector) {
    HOME(R.string.home, Icons.Outlined.Home),
    SETTINGS(R.string.settings, Icons.Outlined.Settings),
    ABOUT(R.string.about, Icons.Outlined.Info),
}
@Composable
fun PrettyLisaApp(model: com.prettylisavpn.android.data.ScreenModel) {
    LocalizedApp {
        Column(Modifier.fillMaxSize().background(Brand.PurpleHeart).imePadding().testTag("app-root")) {
            // The footer owns bottom safe drawing; nested navigation must not reserve it again.
            Box(Modifier.weight(1f).consumeWindowInsets(WindowInsets.safeDrawing.only(WindowInsetsSides.Bottom))) {
                if (model.fixture) FeatureApp(model) else SessionApp(model)
            }
            AppVersionFooter()
        }
    }
}

/** No fixed height: tab labels grow and wrap with the user's font size. */
@Composable
internal fun PhoneNavigation(route: String, navigate: (Destination) -> Unit) {
    // Three narrow columns split whole words at 200% text. Full-width rows keep labels readable.
    if (LocalDensity.current.fontScale >= 1.5f) {
        Column(
            Modifier.fillMaxWidth().background(Brand.Christalle)
                .windowInsetsPadding(WindowInsets.navigationBars.only(WindowInsetsSides.Bottom + WindowInsetsSides.Horizontal))
                .selectableGroup().padding(8.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Destination.entries.forEach { destination ->
                val active = route == destination.name
                Row(
                    Modifier.fillMaxWidth().sizeIn(minHeight = 56.dp).clip(MaterialTheme.shapes.medium)
                        .selectable(selected = active, role = Role.Tab, onClick = { navigate(destination) })
                        .testTag("tab_${destination.name}").padding(horizontal = 12.dp, vertical = 8.dp),
                    horizontalArrangement = Arrangement.spacedBy(16.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Box(
                        Modifier.size(width = 48.dp, height = 36.dp).clip(MaterialTheme.shapes.medium)
                            .background(if (active) Brand.Viking else Brand.Christalle),
                        contentAlignment = Alignment.Center,
                    ) {
                        Icon(destination.icon, null, tint = if (active) Brand.Black else Brand.Mercury)
                    }
                    Text(
                        appString(destination.label), modifier = Modifier.weight(1f),
                        color = if (active) Brand.Viking else Brand.Mercury,
                        style = MaterialTheme.typography.labelMedium,
                    )
                }
            }
        }
        return
    }
    Row(
        Modifier.fillMaxWidth().background(Brand.Christalle)
            .windowInsetsPadding(WindowInsets.navigationBars.only(WindowInsetsSides.Bottom + WindowInsetsSides.Horizontal))
            .selectableGroup().height(IntrinsicSize.Min).padding(horizontal = 8.dp, vertical = 8.dp),
    ) {
        Destination.entries.forEach { destination ->
            val active = route == destination.name
            Column(
                modifier = Modifier.weight(1f).fillMaxHeight().sizeIn(minHeight = 64.dp)
                    .clip(MaterialTheme.shapes.medium)
                    .selectable(selected = active, role = Role.Tab, onClick = { navigate(destination) })
                    .testTag("tab_${destination.name}").padding(horizontal = 4.dp, vertical = 4.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                Box(
                    Modifier.size(width = 48.dp, height = 36.dp).clip(MaterialTheme.shapes.medium)
                        .background(if (active) Brand.Viking else Brand.Christalle),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(destination.icon, contentDescription = null, tint = if (active) Brand.Black else Brand.Mercury)
                }
                Text(
                    appString(destination.label),
                    color = if (active) Brand.Viking else Brand.Mercury,
                    style = MaterialTheme.typography.labelMedium,
                    textAlign = TextAlign.Center,
                )
            }
        }
    }
}

/** Edge pull in either direction: down at the start or up at the end of a list. */
@Composable
internal fun PhoneScreen(tag: String, onRefresh: (() -> Unit)? = null, refreshing: Boolean = false, content: @Composable androidx.compose.foundation.layout.ColumnScope.() -> Unit) {
    val scroll = androidx.compose.foundation.rememberScrollState()
    val refresh by androidx.compose.runtime.rememberUpdatedState(onRefresh)
    val busy by androidx.compose.runtime.rememberUpdatedState(refreshing)
    val threshold = with(LocalDensity.current) { 64.dp.toPx() }
    var pull by androidx.compose.runtime.remember { androidx.compose.runtime.mutableStateOf(0f) }
    val connection = androidx.compose.runtime.remember(scroll, threshold) {
        object : androidx.compose.ui.input.nestedscroll.NestedScrollConnection {
            override fun onPostScroll(consumed: androidx.compose.ui.geometry.Offset, available: androidx.compose.ui.geometry.Offset, source: androidx.compose.ui.input.nestedscroll.NestedScrollSource): androidx.compose.ui.geometry.Offset {
                if (refresh != null && !busy && source == androidx.compose.ui.input.nestedscroll.NestedScrollSource.UserInput) {
                    if ((scroll.value == 0 && available.y > 0) || (scroll.value == scroll.maxValue && available.y < 0)) pull += kotlin.math.abs(available.y)
                    else if (consumed.y != 0f) pull = 0f
                }
                return androidx.compose.ui.geometry.Offset.Zero
            }
            override suspend fun onPreFling(available: androidx.compose.ui.unit.Velocity): androidx.compose.ui.unit.Velocity {
                val trigger = pull >= threshold && !busy
                pull = 0f
                if (trigger) refresh?.invoke()
                return androidx.compose.ui.unit.Velocity.Zero
            }
        }
    }
    val refreshLabel = appString(R.string.ui_refresh)
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.TopCenter) {
        Column(
            modifier = Modifier.widthIn(max = 600.dp).fillMaxSize().testTag(tag)
                .then(if (onRefresh == null) Modifier else Modifier.nestedScroll(connection).semantics {
                    customActions = listOf(androidx.compose.ui.semantics.CustomAccessibilityAction(refreshLabel) { if (!busy) refresh?.invoke(); true })
                })
                .verticalScroll(scroll).padding(horizontal = 20.dp, vertical = 20.dp),
            verticalArrangement = Arrangement.spacedBy(20.dp),
        ) { content() }
        if (refreshing || pull > threshold / 3) androidx.compose.material3.CircularProgressIndicator(
            Modifier.padding(8.dp).size(28.dp).testTag("pull-refresh-indicator"), color = Brand.Viking)
    }
}

@Composable
internal fun ScreenHeading(title: String, onBack: (() -> Unit)? = null) {
    if (onBack == null) Text(title, style = MaterialTheme.typography.headlineLarge, color = Brand.Mercury)
    else Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        IconButton(onClick = onBack, modifier = Modifier.size(48.dp).testTag("support-back")) {
            Icon(Icons.AutoMirrored.Outlined.ArrowBack, appString(R.string.back), tint = Brand.Mercury)
        }
        Text(title, style = MaterialTheme.typography.headlineLarge, color = Brand.Mercury)
    }
}

