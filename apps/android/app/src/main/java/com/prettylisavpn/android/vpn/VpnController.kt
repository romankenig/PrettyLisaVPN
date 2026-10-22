package com.prettylisavpn.android.vpn

import com.prettylisavpn.android.auth.AuthFailure
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.time.Duration

/** UI observes only this safe projection. UP is never mapped directly to CONNECTED. */
enum class VpnPhase { DISCONNECTED, RECONCILING, CONNECTING, VERIFYING, CONNECTED, DISCONNECTING, CLEANUP_PENDING, FAILED }
enum class VpnError { PERMISSION, UNSUPPORTED, VERIFICATION, NETWORK, QUOTA, ACCESS, STORAGE, CLEANUP, UNKNOWN }
data class VpnStatus(val phase: VpnPhase = VpnPhase.DISCONNECTED, val error: VpnError? = null)
interface VpnActions {
    val status: kotlinx.coroutines.flow.StateFlow<VpnStatus>
    /** Called only after system consent, from a foreground UI. */
    fun connect(country: String)
    fun disconnect()
}
interface TunnelRuntime {
    suspend fun start(config: VpnConfig, key: TunnelKey)
    suspend fun stop()
    /** Requires current handshake + VPN-bound DNS/HTTPS + counter growth; no physical fallback. */
    suspend fun verify(config: VpnConfig): Boolean
}
interface TunnelKey { val publicKey: String }
interface VpnJournal {
    fun read(owner: String): PendingVpn?
    fun write(owner: String, value: PendingVpn?)
}
data class PendingVpn(val id: String? = null, val uncertain: Boolean = false)
class VpnFailure(val reason: VpnError) : Exception(reason.name)

/** One process-wide owner shared by UI, service, notification, logout and recovery.
 * Backend has NO POST idempotency key: uncertain creation is reconciled, never replayed.
 */
class VpnController(
    private val api: VpnApi,
    private val runtime: TunnelRuntime,
    private val journal: VpnJournal,
    private val owner: () -> String?,
    private val key: () -> TunnelKey,
    private val scope: CoroutineScope,
    private val elapsed: () -> Long,
    private val serviceIdle: () -> Unit = {},
    private val monitorMillis: Long = 15_000,
) {
    private val mutex = Mutex()
    private val mutable = MutableStateFlow(VpnStatus())
    val status = mutable.asStateFlow()
    private var operation: Job? = null
    private var active: VpnSession? = null
    private var activeOwner: String? = null
    private val cleanupKnown = mutableMapOf<String, String>()
    private var deadline = Long.MAX_VALUE
    private var retry: Job? = null
    private var expiry: Job? = null
    fun rejected(reason: VpnError) { if (active == null && operation?.isActive != true) set(VpnPhase.FAILED, reason) }
    private suspend fun read(id: String) = withContext(Dispatchers.IO) { journal.read(id) }
    private suspend fun save(id: String, value: PendingVpn?) = withContext(Dispatchers.IO) { journal.write(id, value) }
    private fun set(phase: VpnPhase, error: VpnError? = null) { mutable.value = VpnStatus(phase, error) }
    private fun error(e: Exception): VpnError = when (e) {
        is VpnCreateRejected -> error(e.failure)
        is VpnFailure -> e.reason
        is AuthFailure -> when(e.code) {
            "FREE_DAILY_LIMIT_REACHED" -> VpnError.QUOTA
            "device_revoked", "invalid_session", "reauth_required", "invalid_refresh_token", "user_blocked" -> VpnError.ACCESS
            "storage_unavailable" -> VpnError.STORAGE
            else -> VpnError.NETWORK
        }
        else -> VpnError.UNKNOWN
    }
    fun connect(country: String) {
        if (operation?.isActive == true || active != null) return
        if (country != "AUTO" && !country.matches(Regex("[A-Z]{2}"))) return
        retry?.cancel()
        operation = scope.launch {
            mutex.withLock {
                val id = owner() ?: return@withLock
                activeOwner = id
                set(VpnPhase.RECONCILING)
                try {
                    runtime.stop()
                    if (!cleanup(id)) throw VpnFailure(VpnError.CLEANUP)
                    ensureActive()
                    // Create the durable intent BEFORE touching the API, including before key generation.
                    val material = key()
                    save(id, PendingVpn(uncertain = true))
                    set(VpnPhase.CONNECTING)
                    val session = try { api.create(country, material.publicKey) } catch(e: VpnCreateRejected) {
                        save(id, null); throw e
                    } catch(e: AuthFailure) {
                        // Only explicit rejection proves the POST did not allocate a session.
                        if (e.code in setOf("FREE_DAILY_LIMIT_REACHED", "COUNTRY_UNAVAILABLE", "VPN_UNAVAILABLE", "VPN_ADDRESS_POOL_EXHAUSTED")) save(id, null)
                        throw e
                    }
                    // Persist a received UUID even if stop/consent revoke raced with the response.
                    withContext(NonCancellable) { active = session; cleanupKnown[id] = session.id; save(id, PendingVpn(session.id)) }
                    ensureActive()
                    val config = session.config ?: throw VpnFailure(VpnError.UNSUPPORTED)
                    deadline = session.expiresAt?.let { elapsed() + Duration.between(session.serverTime, it).toMillis().coerceAtLeast(0) } ?: Long.MAX_VALUE
                    if (elapsed() >= deadline) throw VpnFailure(VpnError.ACCESS)
                    expiry = scope.launch { if (deadline != Long.MAX_VALUE) { delay((deadline - elapsed()).coerceAtLeast(0)); disconnect() } }
                    runtime.start(config, material)
                    set(VpnPhase.VERIFYING)
                    val verified = withTimeoutOrNull(30_000) {
                        while (!runtime.verify(config)) { delay(1_000) }
                        true
                    } == true
                    if (!verified) throw VpnFailure(VpnError.VERIFICATION)
                    ensureActive()
                    if (owner() != id || elapsed() >= deadline) throw VpnFailure(VpnError.ACCESS)
                    if (api.current()?.id != session.id) throw VpnFailure(VpnError.ACCESS)
                    ensureActive()
                    if (elapsed() >= deadline) throw VpnFailure(VpnError.ACCESS)
                    set(VpnPhase.CONNECTED)
                } catch(e: Exception) {
                    withContext(NonCancellable) {
                        val reason = if (e is CancellationException) null else error(e)
                        finish(id, reason)
                    }
                    if (e is CancellationException) throw e
                }
            }
            if (active != null) monitor()
        }
    }
    private suspend fun monitor() {
        try {
            while (true) {
                delay(minOf(monitorMillis, (deadline - elapsed()).coerceAtLeast(1)))
                mutex.withLock {
                    val session = active ?: return
                    if (elapsed() >= deadline || owner() != activeOwner) throw VpnFailure(VpnError.ACCESS)
                    if (!runtime.verify(session.config!!) ) throw VpnFailure(VpnError.VERIFICATION)
                    if (api.current()?.id != session.id) throw VpnFailure(VpnError.ACCESS)
                }
            }
        } catch(e: CancellationException) { throw e
        } catch(e: Exception) { mutex.withLock { activeOwner?.let { finish(it, error(e)) } } }
    }
    /** Stop publishes immediately; then waits for the current create/start before compensation. */
    fun disconnect() {
        set(VpnPhase.DISCONNECTING)
        operation?.cancel()
        operation = scope.launch { mutex.withLock { (activeOwner ?: owner())?.let { finish(it, null) } ?: run { runtime.stop(); set(VpnPhase.DISCONNECTED); serviceIdle() } } }
    }
    /** Logout must retain refresh credentials while a remote cleanup remains unconfirmed. */
    suspend fun beforeLogout() {
        operation?.cancelAndJoin()
        mutex.withLock {
            val id = activeOwner ?: owner() ?: return
            finish(id, null)
            if (status.value.phase == VpnPhase.CLEANUP_PENDING) throw VpnFailure(VpnError.CLEANUP)
        }
    }
    /** Explicit local-forget may leave remote cleanup pending, but never a live local tunnel. */
    suspend fun beforeForget() {
        try { beforeLogout() } catch (failure: VpnFailure) {
            if (active != null) throw failure
        }
    }
    /** Call only after a successful current-device revoke RPC. The server now owns
     * durable termination, including any late create reserved for this device.
     */
    suspend fun confirmedDeviceRevocation() {
        operation?.cancelAndJoin()
        mutex.withLock {
            val id = activeOwner ?: owner()
            runtime.stop()
            active = null; expiry?.cancel(); expiry = null
            if (id != null) { save(id, null); cleanupKnown.remove(id) }
            activeOwner = null; set(VpnPhase.DISCONNECTED); serviceIdle()
        }
    }
    /** Force-stop/restart never resurrects a remembered Connected state or POST. */
    suspend fun recover() = mutex.withLock {
        if (operation?.isActive == true || active != null) return@withLock
        val id = owner() ?: return@withLock
        activeOwner = id
        set(VpnPhase.RECONCILING)
        finish(id, null)
    }
    private suspend fun finish(id: String, reason: VpnError?) {
        set(VpnPhase.DISCONNECTING)
        // Never remove server allocation while a live local tunnel is still running.
        try { runtime.stop() } catch (_: Exception) { set(VpnPhase.CLEANUP_PENDING, VpnError.CLEANUP); scheduleRetry(); return }
        expiry?.cancel(); expiry = null
        active = null
        val clean = try { cleanup(id) } catch (_: Exception) { false }
        if (clean) {
            activeOwner = null
            set(if (reason == null) VpnPhase.DISCONNECTED else VpnPhase.FAILED, reason)
        } else { set(VpnPhase.CLEANUP_PENDING, VpnError.CLEANUP); scheduleRetry() }
        serviceIdle()
    }
    private suspend fun cleanup(id: String): Boolean {
        if (owner() != id) return false // Never send the old account's UUID under a new account.
        // A storage failure after receiving a UUID must not prevent best-effort DELETE.
        val known = cleanupKnown[id]
        known?.let { api.delete(it) }
        val pending = read(id)
        pending?.id?.takeIf { it != known }?.let { api.delete(it) }
        val current = api.current()
        if (current != null) {
            cleanupKnown[id] = current.id
            try { save(id, PendingVpn(current.id)) } finally { api.delete(current.id) }
        }
        // Null current cannot disprove a timed-out POST still provisioning in the background.
        if (pending?.uncertain == true && current == null && known == null) return false
        save(id, null)
        cleanupKnown.remove(id)
        return true
    }
    private fun scheduleRetry() {
        if (retry?.isActive == true) return
        retry = scope.launch {
            while (status.value.phase == VpnPhase.CLEANUP_PENDING) {
                delay(15_000)
                mutex.withLock { activeOwner?.let { finish(it, null) } }
            }
        }
    }
}
