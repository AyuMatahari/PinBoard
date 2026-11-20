package com.example.ui.components

import android.view.ViewGroup
import android.widget.FrameLayout
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.viewinterop.AndroidView
import androidx.media3.ui.AspectRatioFrameLayout
import androidx.media3.ui.PlayerView
import com.example.util.VideoPlayerManager


@Composable
fun FullscreenVideoPlayer(modifier: Modifier = Modifier) {
    val context = LocalContext.current

    DisposableEffect(Unit) {
        onDispose { VideoPlayerManager.pause() }
    }

    AndroidView(
        modifier = modifier,
        factory = { ctx ->
            FrameLayout(ctx).apply {
                layoutParams = ViewGroup.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.MATCH_PARENT
                )
                val playerView = PlayerView(ctx).apply {
                    player = VideoPlayerManager.getOrCreatePlayer(ctx)
                    useController = true
                    resizeMode = AspectRatioFrameLayout.RESIZE_MODE_FIT
                    setShowBuffering(PlayerView.SHOW_BUFFERING_WHEN_PLAYING)
                    setShowNextButton(false)
                    setShowPreviousButton(false)
                    layoutParams = FrameLayout.LayoutParams(
                        FrameLayout.LayoutParams.MATCH_PARENT,
                        FrameLayout.LayoutParams.MATCH_PARENT
                    )
                }
                addView(playerView)
            }
        },
        update = { container ->
            val pv = container.getChildAt(0) as? PlayerView
            pv?.player = VideoPlayerManager.getOrCreatePlayer(container.context)
        }
    )
}
