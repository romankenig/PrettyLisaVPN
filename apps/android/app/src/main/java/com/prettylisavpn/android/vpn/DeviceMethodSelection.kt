package com.prettylisavpn.android.vpn

import android.content.Context
import androidx.core.content.edit

object DeviceMethodSelection {
    private var instance: MethodSelection? = null
    @Synchronized fun get(context: Context): MethodSelection = instance ?: run {
        val storage = context.applicationContext.getSharedPreferences("vpn-method", Context.MODE_PRIVATE)
        fromStorage(storage).also { instance = it }
    }
    internal fun fromStorage(storage: android.content.SharedPreferences): MethodSelection = MethodSelection(
        read = {
            val legacy = storage.getStringSet("enabled-methods-v1", null)
            val ordered = runCatching {
                storage.getString("ordered-methods-v2", null)?.let {
                    com.google.gson.Gson().fromJson(it, Array<String>::class.java).toList()
                }
            }.getOrNull()
            // Older clients can still change the enabled set after a rollback.
            ordered?.takeIf { it.toSet() == legacy } ?: legacy?.let { selected ->
                connectionMethods.map { it.id }.filter { it in selected }
            }
        },
        write = { value -> storage.edit {
            putStringSet("enabled-methods-v1", value?.toSet())
            if (value == null) remove("ordered-methods-v2")
            else putString("ordered-methods-v2", com.google.gson.Gson().toJson(value))
        } },
    )
}
