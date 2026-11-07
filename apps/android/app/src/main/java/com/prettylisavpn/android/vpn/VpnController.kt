package com.prettylisavpn.android.vpn

import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.channels.Channel

enum class VpnPhase { DISCONNECTED, CONNECTING, CONNECTED, CHECKING, WAITING_NETWORK, RECONNECTING, DISCONNECTING, FAILED }
enum class VpnError { METHODS_EXHAUSTED, CLEANUP, ACCESS, UNSTABLE }
data class VpnAttempt(val method: VpnMethod, val previousMethod: VpnMethod? = null)
data class VpnStatus(val phase: VpnPhase = VpnPhase.DISCONNECTED, val error: VpnError? = null,
    val method: VpnMethod? = null, val attempt: VpnAttempt? = null)
interface VpnActions {
    val status: kotlinx.coroutines.flow.StateFlow<VpnStatus>
    fun connect(country: String)
    fun disconnect()
    fun resetMethods(country: String) {}
}

/** One executor for verified adapters; cleanup fences every fallback attempt. */
class VpnController(
    private val owner: () -> String?,
    private val scope: CoroutineScope,
    private val adapters: List<ConnectionAdapter>,
    private val preference: MethodPreference = MethodPreference(),
    private val recovery: ConnectionAdapter? = null,
    private val enabledMethods: () -> Set<String>? = { null },
    private val healthPolicy: ConnectionHealthPolicy? = null,
    private val elapsedMillis: () -> Long = { System.nanoTime() / 1_000_000 },
) : VpnActions {
    private val mutable = MutableStateFlow(VpnStatus())
    override val status = mutable.asStateFlow()
    private var operation: Job? = null
    private var stopping: Job? = null
    private var active: ConnectionAdapter? = null
    private var recoveredOwner: String? = null
    private var restart: Job? = null
    private var resetRequested = false
    private var intentRevision = 0L
    private val healthWake = Channel<Unit>(Channel.CONFLATED)

    override fun connect(country: String) {
        if (operation?.isActive == true || stopping?.isActive == true || active != null) return
        if (country != "AUTO" && !country.matches(Regex("[A-Z]{2}"))) return
        val id = owner() ?: return
        intentRevision++
        operation = scope.launch {
            val recoveries = ArrayDeque<Long>()
            try {
                while (true) {
                    ensureActive()
                    if (owner() != id) { mutable.value = VpnStatus(); return@launch }
                    var previous: VpnMethod? = null
                    val selected = enabledMethods()
                    val allowed = adapters.filter { selected == null || it.method.id in selected }.associateBy { it.method.id }
                    val ordered = preference.order(allowed.keys.toList()).map { allowed.getValue(it) }
                    var connectedAdapter: ConnectionAdapter? = null
                    for (adapter in ordered) {
                        ensureActive()
                        if (owner() != id) { mutable.value = VpnStatus(); return@launch }
                        mutable.value = VpnStatus(VpnPhase.CONNECTING, attempt = VpnAttempt(adapter.method, previous))
                        var connected = false
                        try {
                            val result = adapter.connect(country)
                            ensureActive()
                            if (owner() == id && result == ConnectionResult.Verified) {
                                active = adapter; connected = true; connectedAdapter = adapter
                                preference.remember(adapter.method.id)
                                mutable.value = VpnStatus(VpnPhase.CONNECTED, method = adapter.method)
                            }
                        } catch (e: CancellationException) { throw e }
                        catch (_: Exception) { /* Continue only after completed cleanup. */ }
                        finally { if (!connected) withContext(NonCancellable) {
                            try { adapter.disconnect() } catch (error: Exception) { active = adapter; throw error }
                        } }
                        if (connected) break
                        previous = adapter.method
                    }
                    val adapter = connectedAdapter ?: run {
                        mutable.value = VpnStatus(VpnPhase.FAILED, VpnError.METHODS_EXHAUSTED, method = previous)
                        return@launch
                    }
                    val policy = healthPolicy ?: return@launch
                    val broken = watchConnection(id, adapter, policy)
                    ensureActive()
                    if (broken) preference.failedAfterConnection(adapter.method.id)
                    mutable.value = VpnStatus(VpnPhase.RECONNECTING, method = adapter.method)
                    withContext(NonCancellable) { adapter.disconnect(); active = null }
                    ensureActive()
                    if (!broken || owner() != id) { mutable.value = VpnStatus(VpnPhase.FAILED, VpnError.ACCESS); return@launch }
                    val instant = elapsedMillis()
                    while (recoveries.isNotEmpty() && instant - recoveries.first() >= policy.recoveryWindowMillis) recoveries.removeFirst()
                    if (recoveries.size >= policy.maxRecoveries) {
                        mutable.value = VpnStatus(VpnPhase.FAILED, VpnError.UNSTABLE); return@launch
                    }
                    recoveries.addLast(instant)
                    delay(policy.recoveryBackoffMillis)
                }
            } catch (e: CancellationException) { throw e }
            catch (_: Exception) { mutable.value = VpnStatus(VpnPhase.FAILED, VpnError.CLEANUP) }
        }
    }
    override fun disconnect() {
        intentRevision++
        resetRequested = false
        restart?.cancel(); restart = null
        stop()
    }
    private fun stop() {
        if (stopping?.isActive == true) return
        operation?.cancel()
        mutable.value = VpnStatus(VpnPhase.DISCONNECTING)
        stopping = scope.launch {
            operation?.join()
            try {
                active?.disconnect(); active = null
                mutable.value = VpnStatus(if (resetRequested) VpnPhase.RECONNECTING else VpnPhase.DISCONNECTED)
            } catch (_: Exception) { mutable.value = VpnStatus(VpnPhase.FAILED, VpnError.CLEANUP) }
        }
    }
    override fun resetMethods(country: String) {
        if (country != "AUTO" && !country.matches(Regex("[A-Z]{2}"))) return
        val id = owner() ?: return
        val revision = ++intentRevision
        restart?.cancel()
        resetRequested = true
        preference.clear()
        stop()
        restart = scope.launch {
            stopping?.join()
            if (intentRevision == revision) {
                resetRequested = false
                if (active == null && mutable.value.phase == VpnPhase.RECONNECTING) {
                    if (owner() == id) connect(country) else mutable.value = VpnStatus(VpnPhase.FAILED, VpnError.ACCESS)
                }
            }
        }
    }
    fun transportLost(method: String) {
        if (healthPolicy != null && active?.method?.id == method && stopping?.isActive != true &&
            mutable.value.phase in setOf(VpnPhase.CONNECTED, VpnPhase.CHECKING, VpnPhase.WAITING_NETWORK)) {
            mutable.value = VpnStatus(VpnPhase.CHECKING, method = active?.method)
            healthWake.trySend(Unit)
        }
    }
    private suspend fun watchConnection(id: String, adapter: ConnectionAdapter, policy: ConnectionHealthPolicy): Boolean {
        var failures = 0
        var wait = policy.intervalMillis
        while (true) {
            withTimeoutOrNull(wait) { healthWake.receive() }
            currentCoroutineContext().ensureActive()
            if (owner() != id) return false
            val health = try { adapter.health() }
                catch (cancel: CancellationException) { throw cancel }
                catch (_: Exception) { TunnelHealth.UNKNOWN }
            currentCoroutineContext().ensureActive()
            if (owner() != id) return false
            when (health) {
                TunnelHealth.HEALTHY -> { failures = 0; mutable.value = VpnStatus(VpnPhase.CONNECTED, method = adapter.method) }
                TunnelHealth.NO_NETWORK -> { failures = 0; mutable.value = VpnStatus(VpnPhase.WAITING_NETWORK, method = adapter.method) }
                TunnelHealth.UNKNOWN -> { failures = 0; mutable.value = VpnStatus(VpnPhase.CHECKING, method = adapter.method) }
                TunnelHealth.UNREACHABLE -> {
                    failures++
                    mutable.value = VpnStatus(VpnPhase.CHECKING, method = adapter.method)
                    if (failures >= policy.failureThreshold) return true
                }
            }
            wait = if (health == TunnelHealth.HEALTHY || health == TunnelHealth.UNKNOWN) policy.intervalMillis else policy.retryMillis
        }
    }
    suspend fun beforeLogout() { disconnect(); stopping?.join() }
    suspend fun beforeForget() = beforeLogout()
    suspend fun confirmedDeviceRevocation() = beforeLogout()
    suspend fun recover() {
        val id = owner() ?: return
        if (recovery == null || recoveredOwner == id || active != null || operation?.isActive == true || stopping?.isActive == true) return
        active = recovery
        mutable.value = VpnStatus(VpnPhase.DISCONNECTING)
        try {
            recovery.recover()
            active = null; recoveredOwner = id; mutable.value = VpnStatus()
        } catch (error: CancellationException) { throw error }
        catch (_: Exception) { mutable.value = VpnStatus(VpnPhase.FAILED, VpnError.CLEANUP) }
    }
}
