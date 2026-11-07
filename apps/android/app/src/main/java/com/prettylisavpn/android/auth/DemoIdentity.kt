package com.prettylisavpn.android.auth

import android.content.Context
import android.provider.Settings
import java.security.MessageDigest

/** App-signing-key + Android-user scoped; stable across ordinary reinstalls.
 * Never read IMEI, advertising ID, contacts, location or another app's identifier.
 */
internal fun demoDeviceKey(context: Context): String = demoDeviceHash(
    Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID)
)

internal fun demoDeviceHash(androidId: String?): String {
    val value = androidId?.lowercase()?.takeIf { it.matches(Regex("[0-9a-f]{1,16}")) && it.toULongOrNull(16) != 0UL }
        ?: throw AuthFailure("demo_identity_unavailable")
    return MessageDigest.getInstance("SHA-256").digest("PrettyLisaVPN/demo/v1:$value".toByteArray(Charsets.UTF_8))
        .joinToString("") { "%02x".format(it) }
}
