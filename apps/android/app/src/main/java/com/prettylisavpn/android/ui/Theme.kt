package com.prettylisavpn.android.ui

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.ExperimentalTextApi
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.prettylisavpn.android.R

/** Shared Windows palette; dynamic system color deliberately does not replace the brand. */
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

@OptIn(ExperimentalTextApi::class)
private val rubik = FontFamily(
    Font(R.font.rubik, FontWeight.Normal, variationSettings = FontVariation.Settings(FontVariation.weight(400))),
    Font(R.font.rubik, FontWeight.Medium, variationSettings = FontVariation.Settings(FontVariation.weight(500))),
    Font(R.font.rubik, FontWeight.SemiBold, variationSettings = FontVariation.Settings(FontVariation.weight(600))),
    Font(R.font.rubik, FontWeight.Bold, variationSettings = FontVariation.Settings(FontVariation.weight(700))),
)

private fun type(size: Int, line: Int, weight: FontWeight = FontWeight.Normal) = TextStyle(
    fontFamily = rubik, fontSize = size.sp, lineHeight = line.sp, fontWeight = weight,
)

private val typography = Typography(
    displayLarge = type(40, 48, FontWeight.SemiBold),
    displayMedium = type(36, 44, FontWeight.SemiBold),
    displaySmall = type(32, 40, FontWeight.SemiBold),
    headlineLarge = type(28, 36, FontWeight.SemiBold),
    headlineMedium = type(26, 34, FontWeight.SemiBold),
    headlineSmall = type(24, 32, FontWeight.SemiBold),
    titleLarge = type(22, 30, FontWeight.SemiBold),
    titleMedium = type(18, 26, FontWeight.SemiBold),
    titleSmall = type(16, 24, FontWeight.SemiBold),
    bodyLarge = type(16, 24),
    bodyMedium = type(14, 22),
    bodySmall = type(12, 18),
    labelLarge = type(16, 24, FontWeight.SemiBold),
    labelMedium = type(12, 16, FontWeight.Medium),
    labelSmall = type(11, 16, FontWeight.Medium),
)

@Composable
fun PrettyLisaTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = lightColorScheme(
            primary = Brand.PurpleHeart,
            onPrimary = Brand.Mercury,
            primaryContainer = Brand.Viking,
            onPrimaryContainer = Brand.Black,
            secondary = Brand.Christalle,
            onSecondary = Brand.Mercury,
            background = Brand.PurpleHeart,
            onBackground = Brand.Mercury,
            surface = Brand.Mercury,
            onSurface = Brand.Black,
            surfaceVariant = Brand.Mercury,
            onSurfaceVariant = Brand.Scorpion,
            surfaceTint = Color.Transparent,
            outline = Brand.PurpleHeart.copy(alpha = 0.45f),
            outlineVariant = Brand.Heliotrope.copy(alpha = 0.4f),
            error = Brand.PersianRed,
            onError = Brand.Mercury,
        ),
        typography = typography,
        shapes = Shapes(
            extraSmall = RoundedCornerShape(6.dp),
            small = RoundedCornerShape(8.dp),
            medium = RoundedCornerShape(12.dp),
            large = RoundedCornerShape(16.dp),
            extraLarge = RoundedCornerShape(24.dp),
        ),
        content = content,
    )
}
