package com.prettylisavpn.android

import android.os.Bundle
import androidx.lifecycle.ViewModelProvider
import com.prettylisavpn.android.data.ScreenModel
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.prettylisavpn.android.ui.PrettyLisaApp
import com.prettylisavpn.android.ui.PrettyLisaTheme

class MainActivity : ComponentActivity() {
    val screenModel: ScreenModel by lazy { ViewModelProvider(this)[ScreenModel::class.java] }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
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
}
