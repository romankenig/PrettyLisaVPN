package com.prettylisavpn.android.vpn

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.content.pm.PackageManager
import android.os.Binder
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import com.prettylisavpn.android.BuildConfig
import com.prettylisavpn.engine.ipc.IEngineControl
import kotlinx.coroutines.*
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/** Only the separately installed, identically signed companion receives private profiles. */
internal class ManagedTunnelClient(private val context: Context, private val lost: () -> Unit) : TunnelRuntime {
    private val packageName = "com.prettylisavpn.engine" + if (BuildConfig.DEBUG) ".dev" else ""
    private val mutex = Mutex()
    private val handler = Handler(Looper.getMainLooper())
    private val owner = Binder()
    private var connection: ServiceConnection? = null
    private var control: IEngineControl? = null
    @Volatile private var owned = false
    var consented = false
        private set
    fun installed(): Boolean = context.packageManager.checkSignatures(context.packageName, packageName) == PackageManager.SIGNATURE_MATCH
    fun consentIntent(): Intent {
        check(installed())
        consented = false
        return Intent().setComponent(ComponentName(packageName, "com.prettylisavpn.engine.ConsentActivity"))
    }
    fun consentResult(accepted: Boolean) { consented = accepted && installed() }
    private suspend fun bind(): IEngineControl = withContext(Dispatchers.Main.immediate) {
        if (!installed()) throw VpnFailure(VpnError.UNSUPPORTED)
        control?.takeIf { it.asBinder().isBinderAlive }?.let { return@withContext it }
        withTimeout(8_000) {
            suspendCancellableCoroutine { continuation ->
                val listener = object : ServiceConnection {
                    override fun onServiceConnected(name: ComponentName, binder: IBinder) {
                        if (!continuation.isActive) return
                        if (name.packageName != packageName || !installed()) {
                            continuation.resumeWithException(VpnFailure(VpnError.UNSUPPORTED)); return
                        }
                        val remote = IEngineControl.Stub.asInterface(binder)
                        control = remote
                        continuation.resume(remote)
                    }
                    override fun onServiceDisconnected(name: ComponentName) {
                        control = null
                        if (owned) lost()
                    }
                    override fun onBindingDied(name: ComponentName) { onServiceDisconnected(name) }
                    override fun onNullBinding(name: ComponentName) {
                        if (continuation.isActive) continuation.resumeWithException(VpnFailure(VpnError.UNSUPPORTED))
                    }
                }
                connection?.let { runCatching { context.unbindService(it) } }
                connection = listener
                continuation.invokeOnCancellation { handler.post { if (connection === listener) release() } }
                if (!context.bindService(Intent().setComponent(ComponentName(packageName, "com.prettylisavpn.engine.ControlService")), listener, Context.BIND_AUTO_CREATE)) {
                    connection = null
                    continuation.resumeWithException(VpnFailure(VpnError.UNSUPPORTED))
                }
            }
        }
    }
    override suspend fun start(config: VpnConfig, key: TunnelKey) = mutex.withLock {
        val profile = config.managed ?: throw VpnFailure(VpnError.UNSUPPORTED)
        if (!consented) throw VpnFailure(VpnError.PERMISSION)
        val remote = bind()
        // A synchronous Binder call completes before cancellation cleanup may start.
        withContext(Dispatchers.IO) {
            if (remote.protocolVersion() != 2) throw VpnFailure(VpnError.UNSUPPORTED)
            owned = true // A lost response still requires confirmed cleanup.
            if (remote.start(profile.privateJson(), owner) != "RUNNING") throw VpnFailure(VpnError.NETWORK)
        }
    }
    override suspend fun stop() = mutex.withLock {
        if (!installed()) {
            if (owned) throw VpnFailure(VpnError.CLEANUP)
            return@withLock
        }
        val remote = bind()
        withContext(Dispatchers.IO) {
            if (remote.protocolVersion() != 2 || !remote.stop() || remote.state() != "DOWN") throw VpnFailure(VpnError.CLEANUP)
            owned = false
        }
    }
    override suspend fun verify(config: VpnConfig): Boolean = mutex.withLock {
        val remote = control ?: return@withLock false
        withContext(Dispatchers.IO) { runCatching { owned && remote.state() == "RUNNING" && remote.verify() && remote.state() == "RUNNING" }.getOrDefault(false) }
    }
    fun release() {
        connection?.let { runCatching { context.unbindService(it) } }
        connection = null; control = null
    }
}
