package com.prettylisavpn.android.data

import android.content.Context
import android.app.ActivityManager
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import android.os.Build
import android.os.PowerManager
import android.os.StatFs
import com.google.gson.Gson
import com.google.gson.JsonObject
import com.prettylisavpn.android.BuildConfig
import com.prettylisavpn.android.diagnostics.AppDiagnostics
import com.prettylisavpn.android.diagnostics.networkDiagnostic
import com.prettylisavpn.android.vpn.*
import java.time.Instant
import java.util.Locale
import java.util.TimeZone

/** Explicit projection; never serialize session/config, arbitrary logs or traffic selections. */
fun androidDiagnostics(context: Context, backendVersion: String?, language: String, plan: String, vpn: VpnStatus? = null): JsonObject {
    val memory = runCatching { ActivityManager.MemoryInfo().also { context.getSystemService(ActivityManager::class.java).getMemoryInfo(it) } }.getOrNull()
    val power = context.getSystemService(PowerManager::class.java)
    val battery = runCatching { context.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED)) }.getOrNull()
    val level = battery?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
    val scale = battery?.getIntExtra(BatteryManager.EXTRA_SCALE, -1) ?: -1
    val current = DeviceTrafficSelection.get(context).current()
    val methods = DeviceMethodSelection.get(context).current() ?: connectionMethods.map { it.id }.toSet()
    val device = linkedMapOf(
        "manufacturer" to Build.MANUFACTURER.take(80), "model" to Build.MODEL.take(120),
        "android_release" to Build.VERSION.RELEASE.take(40), "android_api" to Build.VERSION.SDK_INT,
        "security_patch" to Build.VERSION.SECURITY_PATCH.take(20), "build_id" to Build.ID.take(120),
        "abis" to Build.SUPPORTED_ABIS.take(8).map { it.take(40) }, "app_version_code" to BuildConfig.VERSION_CODE,
        "app_debuggable" to BuildConfig.DEBUG, "memory_available_mb" to memory?.availMem?.div(1024*1024),
        "app_source_sha" to BuildConfig.SOURCE_SHA,
        "memory_total_mb" to memory?.totalMem?.div(1024*1024),
        "storage_available_mb" to runCatching { StatFs(context.filesDir.path).availableBytes / (1024*1024) }.getOrNull(),
        "battery_percent" to if (level >= 0 && scale > 0) (level * 100 / scale).coerceIn(0,100) else null,
        "charging" to battery?.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0)?.let { it != 0 },
        "power_save" to power.isPowerSaveMode, "device_idle" to power.isDeviceIdleMode,
        "battery_optimization_exempt" to power.isIgnoringBatteryOptimizations(context.packageName),
    )
    return Gson().toJsonTree(linkedMapOf(
        "schema_version" to 2, "collected_at" to Instant.now().toString(), "platform" to "ANDROID",
        "frontend_version" to BuildConfig.VERSION_NAME, "backend_version" to backendVersion,
        "language" to language, "timezone" to TimeZone.getDefault().id,
        "plan" to plan.uppercase(Locale.ROOT).takeIf { it in setOf("DEMO","FREE","PREMIUM","PLATINUM") },
        "device" to device, "network" to networkDiagnostic(context),
        "vpn" to linkedMapOf("phase" to vpn?.phase?.name, "method" to (vpn?.method ?: vpn?.attempt?.method)?.id,
            "failure_code" to vpn?.error?.name, "routing_mode" to if (plan.equals("DEMO", true)) "ALL" else current.mode.uppercase(Locale.ROOT), "enabled_methods" to methods.toList().sorted()),
        "logs" to AppDiagnostics.get(context).snapshot(),
    )).asJsonObject.apply {
        if (!has("backend_version")) add("backend_version", com.google.gson.JsonNull.INSTANCE)
        if (!has("plan")) add("plan", com.google.gson.JsonNull.INSTANCE)
    }
}
