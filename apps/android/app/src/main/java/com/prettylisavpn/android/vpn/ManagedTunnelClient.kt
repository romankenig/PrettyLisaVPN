package com.prettylisavpn.android.vpn

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.os.Binder
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import com.google.gson.JsonObject
import com.prettylisavpn.engine.ipc.IEngineControl
import kotlinx.coroutines.*
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/** The unexported engine process belongs to this APK and shares its UID. */
internal class ManagedTunnelClient(private val context: Context, private val lost: () -> Unit) : TunnelRuntime {
    private val packageName = context.packageName
    private val mutex = Mutex()
    private val handler = Handler(Looper.getMainLooper())
    private val owner = Binder()
    private var connection: ServiceConnection? = null
    private var control: IEngineControl? = null
    @Volatile private var owned = false
    @Volatile override var diagnostic: VpnDiagnostic? = null
        private set
    var consented = false
        private set
    fun consentIntent(): Intent {
        consented = false
        return Intent().setComponent(ComponentName(packageName, "com.prettylisavpn.engine.ConsentActivity"))
    }
    fun consentResult(accepted: Boolean) { consented = accepted }
    private suspend fun bind(): IEngineControl = withContext(Dispatchers.Main.immediate) {
        control?.takeIf { it.asBinder().isBinderAlive }?.let { return@withContext it }
        withTimeout(8_000) {
            suspendCancellableCoroutine { continuation ->
                val listener = object : ServiceConnection {
                    override fun onServiceConnected(name: ComponentName, binder: IBinder) {
                        if (!continuation.isActive) return
                        if (name.packageName != packageName) {
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
        diagnostic = null
        val profile = config.managed?.privateJson() ?: JsonObject().apply {
            val secret = (key as? WireGuardKey)?.pair ?: throw VpnFailure(VpnError.STORAGE)
            addProperty("version", 1)
            addProperty("session", config.sessionId ?: throw VpnFailure(VpnError.UNSUPPORTED))
            addProperty("country", config.country ?: throw VpnFailure(VpnError.UNSUPPORTED))
            addProperty("method", "WIREGUARD")
            addProperty("server", config.endpoint)
            addProperty("port", config.port)
            addProperty("secret", secret.privateKey.toBase64())
            addProperty("public_key", config.serverKey)
            addProperty("address", config.address)
        }.toString()
        if (!consented) throw VpnFailure(VpnError.PERMISSION)
        val remote = bind()
        // A synchronous Binder call completes before cancellation cleanup may start.
        withContext(Dispatchers.IO) {
            if (remote.protocolVersion() != 3) throw VpnFailure(VpnError.UNSUPPORTED)
            owned = true // A lost response still requires confirmed cleanup.
            if (remote.start(profile, owner) != "RUNNING") throw VpnFailure(VpnError.NETWORK)
        }
    }
    override suspend fun stop() = mutex.withLock {
        val remote = bind()
        withContext(Dispatchers.IO) {
            if (remote.protocolVersion() != 3 || !remote.stop() || remote.state() != "DOWN") throw VpnFailure(VpnError.CLEANUP)
            owned = false
        }
    }
    override suspend fun verify(config: VpnConfig): Boolean = mutex.withLock {
        val remote = control ?: return@withLock false
        withContext(Dispatchers.IO) {
            runCatching {
                if (!owned || remote.state() != "RUNNING") return@runCatching false
                val result = remote.verify()
                diagnostic = VpnDiagnostic.parse(result)
                result == "VERIFIED" && remote.state() == "RUNNING"
            }.getOrElse { diagnostic = VpnDiagnostic.ENGINE_UNAVAILABLE; false }
        }
    }
    fun release() {
        connection?.let { runCatching { context.unbindService(it) } }
        connection = null; control = null
    }
}
