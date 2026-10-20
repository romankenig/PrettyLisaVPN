package com.prettylisavpn.android.data

/** Release always uses the auth API; no fixture selector or test source. */
object SourceFactory {
    fun create(context: android.content.Context): ScreenSource = LiveSessionFactory.create(context)
}
