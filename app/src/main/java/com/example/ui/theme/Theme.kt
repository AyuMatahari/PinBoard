package com.example.ui.theme

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalContext

private val DarkColorScheme =
  darkColorScheme(
    primary = PinterestRed,
    onPrimary = androidx.compose.ui.graphics.Color.White,
    primaryContainer = PinterestDarkRed,
    onPrimaryContainer = androidx.compose.ui.graphics.Color.White,
    secondary = PinterestLightRed,
    onSecondary = PinterestBlack,
    surface = PinterestDarkSurface,
    onSurface = androidx.compose.ui.graphics.Color.White,
    surfaceVariant = PinterestDarkCard,
    onSurfaceVariant = androidx.compose.ui.graphics.Color(0xFFCCCCCC),
    background = PinterestBlack,
    onBackground = androidx.compose.ui.graphics.Color.White,
  )

private val LightColorScheme =
  lightColorScheme(
    primary = PinterestRed,
    onPrimary = androidx.compose.ui.graphics.Color.White,
    primaryContainer = PinterestLightRed,
    onPrimaryContainer = PinterestDarkRed,
    secondary = PinterestRed,
    onSecondary = androidx.compose.ui.graphics.Color.White,
    surface = PinterestLightSurface,
    onSurface = PinterestTextPrimary,
    surfaceVariant = PinterestLightCard,
    onSurfaceVariant = PinterestTextSecondary,
    background = PinterestLightBg,
    onBackground = PinterestTextPrimary,
  )

@Composable
fun MyApplicationTheme(
  darkTheme: Boolean = isSystemInDarkTheme(),
  // Dynamic color is available on Android 12+
  dynamicColor: Boolean = true,
  content: @Composable () -> Unit,
) {
  val colorScheme =
    when {
      dynamicColor && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S -> {
        val context = LocalContext.current
        if (darkTheme) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
      }

      darkTheme -> DarkColorScheme
      else -> LightColorScheme
    }

  MaterialTheme(colorScheme = colorScheme, typography = Typography, content = content)
}
