package com.prettylisavpn.engine

import android.app.Service
import android.content.Intent
import android.os.Binder
import android.os.IBinder
import android.os.Process

/** Same APK/UID only; no exported engine control endpoint. */
class ControlService : Service() {
    private fun requireOwner() { check(Binder.getCallingUid() == Process.myUid()) }
    private val control = object : IEngineControl.Stub() {
        override fun protocolVersion(): Int { requireOwner(); return 4 }
        override fun start(profile: String, owner: IBinder): String {
            requireOwner()
            if (profile.toByteArray(Charsets.UTF_8).size > 65536) return "UNSUPPORTED_CONFIGURATION"
            return EngineService.instance?.startProfile(profile, owner) ?: "ENGINE_NOT_READY"
        }
        override fun stop(): Boolean { requireOwner(); return EngineService.instance?.stopProfile() ?: true }
        override fun state(): String {
            requireOwner()
            return if (EngineService.instance?.running == true) "RUNNING" else "DOWN"
        }
    }
    override fun onBind(intent: Intent?): IBinder = control
    override fun onUnbind(intent: Intent?): Boolean { EngineService.instance?.requestStop(); return false }
}
