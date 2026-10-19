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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
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

private enum class Destination(val label: Int, val icon: ImageVector) {
    HOME(R.string.home, Icons.Outlined.Home),
    SETTINGS(R.string.settings, Icons.Outlined.Settings),
    ABOUT(R.string.about, Icons.Outlined.Info),
}
private const val SUPPORT = "SUPPORT"

@Composable
fun PrettyLisaApp() {
    val navController = rememberNavController()
    val entry by navController.currentBackStackEntryAsState()
    val route = entry?.destination?.route ?: Destination.HOME.name
    Scaffold(
        modifier = Modifier.imePadding(),
        containerColor = Brand.PurpleHeart,
        contentColor = Brand.Mercury,
        contentWindowInsets = WindowInsets.safeDrawing,
        bottomBar = {
            if (route != SUPPORT) PhoneNavigation(route) { destination ->
                navController.navigate(destination.name) {
                    popUpTo(navController.graph.findStartDestination().id) { saveState = true }
                    launchSingleTop = true
                    restoreState = true
                }
            }
        },
    ) { padding ->
        NavHost(
            navController,
            startDestination = Destination.HOME.name,
            modifier = Modifier.padding(padding).consumeWindowInsets(padding),
        ) {
            composable(Destination.HOME.name) { HomeScreen() }
            composable(Destination.SETTINGS.name) { SettingsScreen() }
            composable(Destination.ABOUT.name) {
                AboutScreen { navController.navigate(SUPPORT) { launchSingleTop = true } }
            }
            composable(SUPPORT) { SupportDraftScreen { navController.popBackStack() } }
        }
    }
    BackHandler(enabled = route != Destination.HOME.name && route != SUPPORT) {
        navController.popBackStack(Destination.HOME.name, inclusive = false)
    }
}

/** No fixed height: tab labels grow and wrap with the user's font size. */
@Composable
private fun PhoneNavigation(route: String, navigate: (Destination) -> Unit) {
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
                        stringResource(destination.label), modifier = Modifier.weight(1f),
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
                    stringResource(destination.label),
                    color = if (active) Brand.Viking else Brand.Mercury,
                    style = MaterialTheme.typography.labelMedium,
                    textAlign = TextAlign.Center,
                )
            }
        }
    }
}

@Composable
internal fun PhoneScreen(tag: String, content: @Composable () -> Unit) {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.TopCenter) {
        Column(
            modifier = Modifier.widthIn(max = 600.dp).fillMaxSize().testTag(tag)
                .verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 20.dp),
            verticalArrangement = Arrangement.spacedBy(20.dp),
        ) { content() }
    }
}

@Composable
internal fun ScreenHeading(title: String, onBack: (() -> Unit)? = null) {
    if (onBack == null) Text(title, style = MaterialTheme.typography.headlineLarge, color = Brand.Mercury)
    else Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        IconButton(onClick = onBack, modifier = Modifier.size(48.dp).testTag("support-back")) {
            Icon(Icons.AutoMirrored.Outlined.ArrowBack, stringResource(R.string.back), tint = Brand.Mercury)
        }
        Text(title, style = MaterialTheme.typography.headlineLarge, color = Brand.Mercury)
    }
}

@Composable
private fun HomeScreen() {
    PhoneScreen("screen_HOME") {
        Image(
            painterResource(R.drawable.prettylisavpn_logo),
            contentDescription = stringResource(R.string.app_name),
            colorFilter = ColorFilter.tint(Brand.Mercury),
            contentScale = ContentScale.Fit,
            modifier = Modifier.fillMaxWidth().height(96.dp).testTag("brand-logo"),
        )
        BrandCard {
            Text(stringResource(R.string.connection), style = MaterialTheme.typography.titleMedium)
            Row(
                Modifier.fillMaxWidth().clip(MaterialTheme.shapes.medium)
                    .background(androidx.compose.ui.graphics.Color.White)
                    .semantics { disabled() }.padding(16.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(Icons.Outlined.LocationOn, null, tint = Brand.PurpleHeart)
                Text(stringResource(R.string.autopilot), style = MaterialTheme.typography.titleSmall)
            }
            BrandActionButton(
                stringResource(R.string.connect), onClick = {}, enabled = false,
                modifier = Modifier.testTag("connect"),
            )
            Text(stringResource(R.string.not_connected), style = MaterialTheme.typography.titleSmall)
            Text(stringResource(R.string.connection_unavailable), style = MaterialTheme.typography.bodyMedium, color = Brand.Scorpion)
        }
        BrandCard {
            Text(stringResource(R.string.what_to_protect), style = MaterialTheme.typography.titleMedium)
            TrafficOption(R.string.all_traffic, R.string.all_traffic_description, true)
            TrafficOption(R.string.selected_traffic, R.string.selected_traffic_description, false)
            TrafficOption(R.string.except_traffic, R.string.except_traffic_description, false)
        }
    }
}

@Composable
private fun TrafficOption(title: Int, subtitle: Int, active: Boolean) {
    Row(
        Modifier.fillMaxWidth().clip(MaterialTheme.shapes.medium)
            .background(if (active) Brand.Viking.copy(alpha = 0.22f) else androidx.compose.ui.graphics.Color.White.copy(alpha = 0.6f))
            .semantics { selected = active; if (!active) disabled() }.padding(14.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        if (active) Icon(Icons.Outlined.Check, null, tint = Brand.PurpleHeart, modifier = Modifier.size(24.dp))
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(stringResource(title), style = MaterialTheme.typography.titleSmall, color = if (active) Brand.Black else Brand.Scorpion)
            Text(stringResource(subtitle), style = MaterialTheme.typography.bodySmall, color = Brand.Scorpion)
            if (!active) Text(stringResource(R.string.soon), style = MaterialTheme.typography.labelSmall, color = Brand.PurpleHeart)
        }
    }
}

@Composable
private fun SettingsScreen() {
    PhoneScreen("screen_SETTINGS") {
        ScreenHeading(stringResource(R.string.settings))
        BrandCard {
            UnavailableSetting(R.string.subscription)
            HorizontalDivider(color = Brand.PurpleHeart.copy(alpha = 0.18f))
            UnavailableSetting(R.string.devices)
        }
        BrandCard {
            Text(stringResource(R.string.appearance), style = MaterialTheme.typography.titleMedium)
            Text(stringResource(R.string.appearance_value), style = MaterialTheme.typography.bodyLarge)
        }
    }
}

@Composable
private fun UnavailableSetting(label: Int) {
    Column(Modifier.fillMaxWidth().semantics { disabled() }, verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(stringResource(label), style = MaterialTheme.typography.titleSmall)
        Text(stringResource(R.string.feature_unavailable), style = MaterialTheme.typography.bodyMedium, color = Brand.Scorpion)
    }
}

@Composable
private fun AboutScreen(openSupport: () -> Unit) {
    PhoneScreen("screen_ABOUT") {
        ScreenHeading(stringResource(R.string.about))
        BrandCard {
            Text(stringResource(R.string.app_name), style = MaterialTheme.typography.titleLarge)
            Text(stringResource(R.string.android_version, BuildConfig.VERSION_NAME), style = MaterialTheme.typography.bodyLarge)
            Text(stringResource(R.string.source_commit, BuildConfig.SOURCE_SHA.take(12)), style = MaterialTheme.typography.bodySmall, modifier = Modifier.testTag("build-source"))
            HorizontalDivider(color = Brand.PurpleHeart.copy(alpha = 0.18f))
            Text(stringResource(R.string.backend_label), style = MaterialTheme.typography.titleSmall)
            Text(stringResource(R.string.backend_unavailable), color = Brand.Scorpion)
        }
        BrandCard {
            Text(stringResource(R.string.help), style = MaterialTheme.typography.titleMedium)
            Text(stringResource(R.string.help_description), style = MaterialTheme.typography.bodyMedium)
            BrandActionButton(stringResource(R.string.contact_support), openSupport, Modifier.testTag("open-support"))
        }
        Text(stringResource(R.string.dedication), style = MaterialTheme.typography.bodySmall, color = Brand.Mercury.copy(alpha = 0.85f))
    }
}
