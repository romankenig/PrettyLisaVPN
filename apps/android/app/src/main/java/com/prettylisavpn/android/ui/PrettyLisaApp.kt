package com.prettylisavpn.android.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.sizeIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.prettylisavpn.android.BuildConfig
import com.prettylisavpn.android.R

private enum class Destination(val label: Int, val icon: ImageVector) {
    HOME(R.string.home, Icons.Default.Home),
    SETTINGS(R.string.settings, Icons.Default.Settings),
    ABOUT(R.string.about, Icons.Default.Info),
}

@Composable
fun PrettyLisaApp() {
    val navController = rememberNavController()
    val entry by navController.currentBackStackEntryAsState()
    val route = entry?.destination?.route ?: Destination.HOME.name
    Scaffold(
        bottomBar = {
            NavigationBar(containerColor = Brand.Christalle) {
                Destination.entries.forEach { destination ->
                    NavigationBarItem(
                        selected = route == destination.name,
                        onClick = {
                            navController.navigate(destination.name) {
                                popUpTo(navController.graph.findStartDestination().id) {
                                    saveState = true
                                }
                                launchSingleTop = true
                                restoreState = true
                            }
                        },
                        modifier = Modifier.testTag("tab_${destination.name}"),
                        icon = { Icon(destination.icon, contentDescription = null) },
                        label = { Text(stringResource(destination.label)) },
                        colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = Brand.Black,
                            selectedTextColor = Brand.Viking,
                            indicatorColor = Brand.Viking,
                            unselectedIconColor = Brand.Mercury,
                            unselectedTextColor = Brand.Mercury,
                        ),
                    )
                }
            }
        },
    ) { padding ->
        NavHost(navController, startDestination = Destination.HOME.name, modifier = Modifier.padding(padding)) {
            composable(Destination.HOME.name) { HomeScreen() }
            composable(Destination.SETTINGS.name) { SettingsScreen() }
            composable(Destination.ABOUT.name) { AboutScreen() }
        }
    }
    // Each top-level tab returns directly Home; Home uses the system exit behavior.
    BackHandler(enabled = route != Destination.HOME.name) {
        navController.popBackStack(Destination.HOME.name, inclusive = false)
    }
}

@Composable
private fun Screen(tag: String, content: @Composable () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().testTag(tag)
            .verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(20.dp),
    ) { content() }
}

@Composable
private fun InformationCard(content: @Composable () -> Unit) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Brand.Mercury, contentColor = Brand.Black),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) { content() }
    }
}

@Composable
private fun HomeScreen() {
    Screen("screen_HOME") {
        InformationCard {
            Image(
                painterResource(R.drawable.prettylisavpn_logo),
                contentDescription = stringResource(R.string.app_name),
                modifier = Modifier.fillMaxWidth().height(156.dp),
            )
        }
        Text(stringResource(R.string.welcome), style = MaterialTheme.typography.headlineSmall)
        InformationCard {
            Text(stringResource(R.string.not_connected), style = MaterialTheme.typography.titleLarge)
            Text(stringResource(R.string.bootstrap_notice), style = MaterialTheme.typography.bodyLarge)
            Button(
                onClick = {},
                enabled = false,
                colors = ButtonDefaults.buttonColors(
                    disabledContainerColor = Brand.Black.copy(alpha = 0.12f),
                    disabledContentColor = Brand.Scorpion,
                ),
                contentPadding = PaddingValues(16.dp),
                modifier = Modifier.fillMaxWidth().sizeIn(minHeight = 48.dp).testTag("connect"),
            ) { Text(stringResource(R.string.connect)) }
        }
    }
}

@Composable
private fun SettingsScreen() {
    Screen("screen_SETTINGS") {
        Text(stringResource(R.string.settings), style = MaterialTheme.typography.headlineLarge)
        InformationCard {
            Text(stringResource(R.string.appearance), style = MaterialTheme.typography.titleMedium)
            Text(stringResource(R.string.appearance_value))
        }
        Text(stringResource(R.string.settings_notice), style = MaterialTheme.typography.bodyLarge)
    }
}

@Composable
private fun AboutScreen() {
    Screen("screen_ABOUT") {
        Text(stringResource(R.string.about), style = MaterialTheme.typography.headlineLarge)
        InformationCard {
            Text(stringResource(R.string.app_name), style = MaterialTheme.typography.titleLarge)
            Text(stringResource(R.string.android_version, BuildConfig.VERSION_NAME))
            Text(stringResource(R.string.source_commit, BuildConfig.SOURCE_SHA.take(12)))
            Text(stringResource(R.string.backend_label), style = MaterialTheme.typography.titleMedium)
            Text(stringResource(R.string.backend_unavailable))
        }
        Text(stringResource(R.string.about_notice), style = MaterialTheme.typography.bodyLarge)
    }
}
