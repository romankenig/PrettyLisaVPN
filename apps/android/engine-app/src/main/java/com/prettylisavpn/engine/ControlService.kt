package com.prettylisavpn.engine

import android.app.Service
import android.content.Intent
import android.os.IBinder
import com.prettylisavpn.engine.ipc.IEngineControl

/** The signature permission is complemented by a package/UID check on every IPC. */
class ControlService : Service() {
    private val control = object : IEngineControl.Stub() {
        override fun protocolVersion(): Int { Access.requireClient(this@ControlService); return 2 }
        override fun start(profile: String, owner: IBinder): String {
            Access.requireClient(this@ControlService)
            if (profile.toByteArray(Charsets.UTF_8).size > 65536) return "UNSUPPORTED_CONFIGURATION"
            return EngineService.instance?.startProfile(profile, owner) ?: "PERMISSION_REQUIRED"
        }
        override fun stop(): Boolean {
            Access.requireClient(this@ControlService)
            return EngineService.instance?.stopProfile() ?: true
        }
        override fun state(): String {
            Access.requireClient(this@ControlService)
            return if (EngineService.instance?.running == true) "RUNNING" else "DOWN"
        }
        override fun verify(): Boolean {
            Access.requireClient(this@ControlService)
            return EngineService.instance?.verifyInternet() == true
        }
    }
    override fun onBind(intent: Intent?): IBinder = control
    override fun onUnbind(intent: Intent?): Boolean { EngineService.instance?.requestStop(); return false }
}
