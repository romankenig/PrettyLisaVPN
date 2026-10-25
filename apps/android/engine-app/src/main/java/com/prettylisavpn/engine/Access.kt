package com.prettylisavpn.engine

import android.content.Context
import android.os.Binder
import android.os.Process

internal object Access {
    fun requireClient(context: Context) {
        val uid = Binder.getCallingUid()
        if (uid != Process.myUid() || context.applicationInfo.uid != uid)
            throw SecurityException("CLIENT_NOT_AUTHORIZED")
    }
    fun isClientActivity(context: Context, caller: String?): Boolean = caller == context.packageName
}
