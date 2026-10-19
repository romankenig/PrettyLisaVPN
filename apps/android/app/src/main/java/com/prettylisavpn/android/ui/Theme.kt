package com.prettylisavpn.android.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import com.prettylisavpn.android.R

object Brand {
    val Black = Color(0xFF010101)
    val Mercury = Color(0xFFE4E4E4)
    val PurpleHeart = Color(0xFF5F22D9)
    val Christalle = Color(0xFF2C016D)
    val DustyGray = Color(0xFF9C9C9C)
    val Galliano = Color(0xFFD7AD0D)
    val Scorpion = Color(0xFF5B5B5B)
    val Viking = Color(0xFF51D6CA)
    val Heliotrope = Color(0xFFAC73FF)
    val PersianRed = Color(0xFFC82B28)
}

private val rubik = FontFamily(Font(R.font.rubik))
private val base = Typography()
private val typography = Typography(
    headlineLarge = base.headlineLarge.copy(fontFamily = rubik),
    headlineSmall = base.headlineSmall.copy(fontFamily = rubik),
    titleLarge = base.titleLarge.copy(fontFamily = rubik),
    titleMedium = base.titleMedium.copy(fontFamily = rubik),
    bodyLarge = base.bodyLarge.copy(fontFamily = rubik),
    bodyMedium = base.bodyMedium.copy(fontFamily = rubik),
    labelLarge = base.labelLarge.copy(fontFamily = rubik),
    labelMedium = base.labelMedium.copy(fontFamily = rubik),
)

@Composable
fun PrettyLisaTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = darkColorScheme(
            primary = Brand.Viking,
            onPrimary = Brand.Black,
            primaryContainer = Brand.PurpleHeart,
            onPrimaryContainer = Brand.Mercury,
            secondary = Brand.Heliotrope,
            background = Brand.Christalle,
            onBackground = Brand.Mercury,
            surface = Brand.Christalle,
            onSurface = Brand.Mercury,
            surfaceVariant = Brand.Mercury,
            onSurfaceVariant = Brand.Scorpion,
            error = Brand.PersianRed,
        ),
        typography = typography,
        content = content,
    )
}
