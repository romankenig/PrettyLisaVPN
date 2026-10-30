package com.prettylisavpn.android.vpn

import android.content.Context
import android.annotation.SuppressLint

object DeviceTrafficSelection {
    private var instance: TrafficPreference? = null
    // KTX edit(commit=true) discards commit's result; rules must not appear saved on disk failure.
    @SuppressLint("UseKtx")
    @Synchronized fun get(context: Context): TrafficPreference = instance ?: run {
        val storage = context.applicationContext.getSharedPreferences("traffic-rules", Context.MODE_PRIVATE)
        TrafficPreference(read = { storage.getString("selection-v1", null) }, write = { value ->
            check(storage.edit().putString("selection-v1", value).commit()) { "TRAFFIC_SAVE_FAILED" }
        }).also { instance = it }
    }
}
