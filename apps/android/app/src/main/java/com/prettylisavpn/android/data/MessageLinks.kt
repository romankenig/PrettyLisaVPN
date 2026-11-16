package com.prettylisavpn.android.data

import java.net.URI

/** Validate again immediately before ACTION_VIEW. Never attach auth or log the URL. */
fun validMessageUrl(raw: String): Boolean = runCatching {
    require(raw.length <= 2048 && raw.startsWith("https://"))
    require(raw.none { it.isWhitespace() || it.isISOControl() || it == '\\' })
    val uri = URI(raw)
    require(!uri.host.isNullOrBlank() && uri.rawUserInfo == null && uri.port in setOf(-1, 443))
    true
}.getOrDefault(false)
