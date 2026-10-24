package com.prettylisavpn.engine

import android.content.Context
import android.content.pm.PackageManager
import android.os.Binder
import android.os.Process

internal object Access {
    val clientPackage = "com.prettylisavpn.android" + if (BuildConfig.DEBUG) ".dev" else ""
    fun requireClient(context: Context) {
        val uid = Binder.getCallingUid()
        if (context.packageManager.getPackagesForUid(uid)?.contains(clientPackage) != true ||
            context.packageManager.checkSignatures(uid, Process.myUid()) != PackageManager.SIGNATURE_MATCH)
            throw SecurityException("CLIENT_NOT_AUTHORIZED")
    }
    fun isClientActivity(context: Context, caller: String?): Boolean = caller == clientPackage &&
        context.packageManager.checkSignatures(clientPackage, context.packageName) == PackageManager.SIGNATURE_MATCH
}
