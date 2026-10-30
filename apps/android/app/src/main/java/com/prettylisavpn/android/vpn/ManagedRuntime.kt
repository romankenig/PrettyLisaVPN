package com.prettylisavpn.android.vpn

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.os.Binder
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import com.prettylisavpn.engine.ControlService
import com.prettylisavpn.engine.EngineService
import com.prettylisavpn.engine.IEngineControl
import kotlinx.coroutines.*
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

internal class ManagedRuntime(private val context: Context, private val lost: () -> Unit) {
    private val mutex = Mutex()
    private val handler = Handler(Looper.getMainLooper())
    private val owner = Binder()
    private var connection: ServiceConnection? = null
    private var control: IEngineControl? = null
    @Volatile private var owned = false
    val isOwned get() = owned
    private suspend fun bind(): IEngineControl = withContext(Dispatchers.Main.immediate) {
        control?.takeIf { it.asBinder().isBinderAlive }?.let { return@withContext it }
        withTimeout(8_000) {
            suspendCancellableCoroutine { continuation ->
                val listener = object : ServiceConnection {
                    override fun onServiceConnected(name: ComponentName, binder: IBinder) {
                        if (!continuation.isActive) return
                        if (name.packageName != context.packageName) {
                            continuation.resumeWithException(IllegalStateException("ENGINE_OWNER_MISMATCH")); return
                        }
                        control = IEngineControl.Stub.asInterface(binder)
                        continuation.resume(requireNotNull(control))
                    }
                    override fun onServiceDisconnected(name: ComponentName) {
                        control = null
                        if (owned) lost()
                    }
                    override fun onBindingDied(name: ComponentName) { onServiceDisconnected(name) }
                    override fun onNullBinding(name: ComponentName) {
                        if (continuation.isActive) continuation.resumeWithException(IllegalStateException("ENGINE_UNAVAILABLE"))
                    }
                }
                release(); connection = listener
                continuation.invokeOnCancellation { handler.post { if (connection === listener) release() } }
                if (!context.bindService(Intent(context, ControlService::class.java), listener, Context.BIND_AUTO_CREATE)) {
                    connection = null
                    continuation.resumeWithException(IllegalStateException("ENGINE_UNAVAILABLE"))
                }
            }
        }
    }
    suspend fun start(profile: String) = mutex.withLock {
        context.startForegroundService(Intent(context, EngineService::class.java))
        val remote = bind()
        withContext(Dispatchers.IO) {
            check(remote.protocolVersion() == 4)
            owned = true // An ambiguous native reply still requires confirmed local cleanup.
            var result = "ENGINE_NOT_READY"
            repeat(30) {
                if (result == "ENGINE_NOT_READY") { result = remote.start(profile, owner); if (result == "ENGINE_NOT_READY") delay(100) }
            }
            check(result == "RUNNING") { "ENGINE_START_FAILED" }
        }
    }
    suspend fun isUp(): Boolean = withContext(Dispatchers.IO) { owned && control?.state() == "RUNNING" }
    suspend fun stop() = mutex.withLock {
        // A dead Binder closes the process-owned tunnel; connect to a surviving
        // service to verify it is stopped, including recovery after a lost reply.
        val remote = bind()
        withContext(Dispatchers.IO) {
            check(remote.protocolVersion() == 4 && remote.stop() && remote.state() == "DOWN") { "ENGINE_CLEANUP_FAILED" }
            owned = false
        }
        release()
        context.stopService(Intent(context, EngineService::class.java))
    }
    private fun release() {
        connection?.let { runCatching { context.unbindService(it) } }
        connection = null; control = null
    }
}
