package com.prettylisavpn.android.data

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Build
import com.google.gson.GsonBuilder
import com.prettylisavpn.android.BuildConfig
import java.time.Instant
import java.util.TimeZone

/** Explicit allowlist. No credentials, identifiers, IP, SSID, paths or traffic history. */
fun androidDiagnostics(context: Context, backendVersion: String?, language: String, plan: String, vpn: com.prettylisavpn.android.vpn.VpnStatus? = null): String {
    val connectivity = context.getSystemService(ConnectivityManager::class.java)
    val capabilities = runCatching { connectivity.getNetworkCapabilities(connectivity.activeNetwork) }.getOrNull()
    val network = when {
        capabilities == null -> "unavailable"
        capabilities.hasTransport(NetworkCapabilities.TRANSPORT_VPN) -> "vpn"
        capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "wifi"
        capabilities.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> "cellular"
        capabilities.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) -> "ethernet"
        else -> "other"
    }
    return GsonBuilder().serializeNulls().setPrettyPrinting().create().toJson(linkedMapOf(
        "schema_version" to 1, "collected_at" to Instant.now().toString(),
        "platform" to "ANDROID", "frontend_version" to BuildConfig.VERSION_NAME,
        "backend_version" to backendVersion, "android_api" to Build.VERSION.SDK_INT,
        "language" to language, "timezone" to TimeZone.getDefault().id,
        "plan" to plan.uppercase(java.util.Locale.ROOT).takeIf { it in setOf("FREE", "PREMIUM", "PLATINUM") },
        "network" to network, "vpn_runtime" to if (vpn == null) "unavailable" else "placeholders", "vpn_tunnel" to (vpn?.phase?.name?.lowercase(java.util.Locale.ROOT) ?: "not_started"),
    ))
}

/** Existing server diagnostics schema is WINDOWS-only. This opt-in text is not mislabelled. */
fun supportDescription(description: String, diagnostics: String?): String =
    if (diagnostics == null) description.trim() else description.trim() + "\n\n[PrettyLisaVPN Android diagnostics]\n" + diagnostics
