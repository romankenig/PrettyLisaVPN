package com.prettylisavpn.engine

import android.app.Activity
import android.content.Intent
import android.net.VpnService
import android.os.Bundle

/** Internal activity of the single APK; profiles never enter intents. */
@Suppress("DEPRECATION")
class ConsentActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!Access.isClientActivity(this, callingPackage)) { setResult(RESULT_CANCELED); finish(); return }
        val intent = VpnService.prepare(this)
        if (intent == null) ready() else if (savedInstanceState == null) startActivityForResult(intent, 1)
    }
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == 1 && resultCode == RESULT_OK && VpnService.prepare(this) == null) ready()
        else { setResult(RESULT_CANCELED); finish() }
    }
    private fun ready() {
        try {
            startForegroundService(Intent(this, EngineService::class.java))
            setResult(RESULT_OK)
        } catch (_: Exception) { setResult(RESULT_CANCELED) }
        finish()
    }
}
