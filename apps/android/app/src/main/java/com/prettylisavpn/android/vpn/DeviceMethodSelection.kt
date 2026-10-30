package com.prettylisavpn.android.vpn

import android.content.Context
import androidx.core.content.edit

object DeviceMethodSelection {
    private var instance: MethodSelection? = null
    @Synchronized fun get(context: Context): MethodSelection = instance ?: run {
        val storage = context.applicationContext.getSharedPreferences("vpn-method", Context.MODE_PRIVATE)
        MethodSelection(
            read = { storage.getStringSet("enabled-methods-v1", null)?.toSet() },
            write = { value -> storage.edit { putStringSet("enabled-methods-v1", value) } },
        ).also { instance = it }
    }
}
