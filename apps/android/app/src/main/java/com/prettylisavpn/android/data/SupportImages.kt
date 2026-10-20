package com.prettylisavpn.android.data

import android.content.Context
import android.graphics.BitmapFactory
import android.net.Uri
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/** Only explicit SAF selections, with no broad storage permission and no client filenames. */
suspend fun readSupportImages(context: Context, uris: List<String>): List<SupportUpload> = withContext(Dispatchers.IO) {
    try {
        require(uris.size <= 3)
        var total = 0
        uris.map { value ->
            val uri = Uri.parse(value); require(uri.scheme == "content")
            val media = context.contentResolver.getType(uri); require(media in setOf("image/png", "image/jpeg", "image/webp"))
            val stream = checkNotNull(context.contentResolver.openInputStream(uri))
            val bytes = stream.use { input ->
                val output = java.io.ByteArrayOutputStream(); val buffer = ByteArray(8192)
                while (output.size() <= 5*1024*1024) { val n = input.read(buffer, 0, minOf(buffer.size, 5*1024*1024+1-output.size())); if (n < 0) break; output.write(buffer, 0, n) }
                output.toByteArray()
            }
            total += bytes.size; require(bytes.isNotEmpty() && bytes.size <= 5*1024*1024 && total <= 10*1024*1024)
            val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
            require(bounds.outWidth in 1..8192 && bounds.outHeight in 1..8192 && bounds.outWidth.toLong()*bounds.outHeight <= 12_000_000)
            SupportUpload(media!!, java.util.Base64.getEncoder().encodeToString(bytes))
        }
    } catch (_: Exception) { throw SourceFailure("Choose up to 3 PNG, JPEG or WebP images, at most 5 MB each and 10 MB total.") }
}
