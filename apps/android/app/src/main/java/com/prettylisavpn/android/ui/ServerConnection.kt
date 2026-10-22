package com.prettylisavpn.android.ui

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.prettylisavpn.android.R
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.*

/** Observe the default route; public /version, not Android validation probes, decides reachability. */
private fun internet(context: Context): Flow<Boolean> = callbackFlow {
    val manager = context.getSystemService(ConnectivityManager::class.java)
    fun update() {
        val capabilities = manager.getNetworkCapabilities(manager.activeNetwork)
        // Captive portals and blocked OS validation are resolved by the bounded HTTPS probe.
        trySend(capabilities?.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) == true)
    }
    val callback = object : ConnectivityManager.NetworkCallback() {
        override fun onAvailable(network: Network) = update()
        override fun onLost(network: Network) = update()
        override fun onCapabilitiesChanged(network: Network, capabilities: NetworkCapabilities) = update()
    }
    manager.registerDefaultNetworkCallback(callback)
    update()
    awaitClose { manager.unregisterNetworkCallback(callback) }
}.distinctUntilChanged()

/** Probe only public GET /version; no authentication, device IDs or mutations. */
@OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
internal fun serverConnections(network: Flow<Boolean>, intervalMillis: Long = 15_000, probe: suspend () -> Boolean): Flow<Boolean> =
    network.distinctUntilChanged().flatMapLatest { available ->
        if (!available) flowOf(false) else flow {
            while (true) {
                val reachable = try { probe() } catch (e: CancellationException) { throw e } catch (_: Exception) { false }
                emit(reachable)
                delay(intervalMillis)
            }
        }
    }.distinctUntilChanged()

@Composable
internal fun ServerConnectionNotice(enabled: Boolean) {
    val presentation = LocalPresentation.current
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    var started by remember(lifecycle) { mutableStateOf(lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) }
    DisposableEffect(lifecycle) {
        val observer = LifecycleEventObserver { _, _ -> started = lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED) }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer) }
    }
    var connected by remember { mutableStateOf<Boolean?>(null) }
    val context = androidx.compose.ui.platform.LocalContext.current.applicationContext
    LaunchedEffect(enabled, started) {
        if (enabled && started && PresentationStore.networkEnabled)
            serverConnections(internet(context)) { presentation.refreshServer() }.collect { connected = it }
    }
    ConnectionNotice(connected)
}

@Composable
internal fun ConnectionNotice(connected: Boolean?) {
    if (connected == false) Text(appString(R.string.server_connection_lost),
        Modifier.fillMaxWidth().background(Brand.Christalle).padding(horizontal = 12.dp, vertical = 8.dp)
            .testTag("server-connection-notice").semantics { liveRegion = LiveRegionMode.Polite },
        color = Brand.Galliano, style = MaterialTheme.typography.bodySmall)
}
