package com.prettylisavpn.android

import android.os.Bundle
import android.app.Activity
import androidx.core.content.edit
import androidx.activity.result.contract.ActivityResultContracts
import com.prettylisavpn.android.vpn.VpnPermission
import kotlinx.coroutines.CompletableDeferred
import androidx.lifecycle.ViewModelProvider
import com.prettylisavpn.android.data.ScreenModel
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.prettylisavpn.android.ui.PrettyLisaApp
import com.prettylisavpn.android.ui.PrettyLisaTheme

class MainActivity : ComponentActivity() {
    private var vpnConsent: CompletableDeferred<Boolean>? = null
    private var notificationConsent: CompletableDeferred<Unit>? = null
    private val notificationLauncher = registerForActivityResult(ActivityResultContracts.RequestPermission()) {
        notificationConsent?.complete(Unit)
        notificationConsent = null
    }
    private val vpnLauncher = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) {
        vpnConsent?.complete(it.resultCode == Activity.RESULT_OK)
        vpnConsent = null
    }
    val screenModel: ScreenModel by lazy { ViewModelProvider(this, object : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : androidx.lifecycle.ViewModel> create(modelClass: Class<T>): T =
            ScreenModel(com.prettylisavpn.android.data.SourceFactory.create(applicationContext)) as T
    })[ScreenModel::class.java] }

    override fun onStart() {
        super.onStart()
        if (!screenModel.fixture) com.prettylisavpn.android.diagnostics.AppDiagnostics.get(applicationContext).record(com.prettylisavpn.android.diagnostics.DiagnosticKind.APP_FOREGROUND)
        if (!screenModel.fixture && screenModel.state.value.data.signedIn) screenModel.load(com.prettylisavpn.android.data.Area.HOME)
    }
    override fun onStop() {
        if (!screenModel.fixture) com.prettylisavpn.android.diagnostics.AppDiagnostics.get(applicationContext).record(com.prettylisavpn.android.diagnostics.DiagnosticKind.APP_BACKGROUND)
        super.onStop()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        VpnPermission.launch = { intent ->
            val answer = CompletableDeferred<Boolean>()
            vpnConsent?.complete(false)
            vpnConsent = answer
            vpnLauncher.launch(intent)
            answer.await()
        }
        VpnPermission.launchNotifications = {
            val preferences = getSharedPreferences("vpn-notifications", MODE_PRIVATE)
            if (android.os.Build.VERSION.SDK_INT >= 33 &&
                checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) != android.content.pm.PackageManager.PERMISSION_GRANTED &&
                !preferences.getBoolean("asked", false)) {
                // Denial never blocks VPN or causes another prompt on fallback.
                preferences.edit { putBoolean("asked", true) }
                val answer = CompletableDeferred<Unit>()
                notificationConsent = answer
                notificationLauncher.launch(android.Manifest.permission.POST_NOTIFICATIONS)
                answer.await()
            }
        }
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(android.graphics.Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.dark(android.graphics.Color.TRANSPARENT),
        )
        setContent {
            PrettyLisaTheme {
                PrettyLisaApp(screenModel)
            }
        }
    }
    override fun onDestroy() {
        vpnConsent?.complete(false)
        VpnPermission.launch = null
        notificationConsent?.complete(Unit)
        VpnPermission.launchNotifications = null
        super.onDestroy()
    }
}
