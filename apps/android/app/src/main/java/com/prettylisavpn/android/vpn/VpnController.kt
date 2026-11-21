package com.prettylisavpn.android.vpn

import com.prettylisavpn.android.auth.AuthFailure
import com.prettylisavpn.android.data.readWithNetworkGrace
import com.prettylisavpn.android.diagnostics.*

import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.channels.Channel

enum class VpnPhase { DISCONNECTED, CONNECTING, CONNECTED, CHECKING, WAITING_NETWORK, RECONNECTING, DISCONNECTING, FAILED }
enum class VpnError { METHODS_EXHAUSTED, CLEANUP, ACCESS, UNSTABLE, DEMO_LIMIT, FREE_LIMIT }
/** Preserve the existing support API v2 vocabulary. */
internal fun supportFailureCode(error: VpnError?): String? = if (error == VpnError.FREE_LIMIT) "ACCESS" else error?.name
data class VpnAttempt(val method: VpnMethod, val previousMethod: VpnMethod? = null)
data class VpnStatus(val phase: VpnPhase = VpnPhase.DISCONNECTED, val error: VpnError? = null,
    val method: VpnMethod? = null, val attempt: VpnAttempt? = null, val egress: VpnEgress? = null)
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
    private val enabledMethods: () -> Collection<String>? = { null },
    private val healthPolicy: ConnectionHealthPolicy? = null,
    private val elapsedMillis: () -> Long = { System.nanoTime() / 1_000_000 },
    private val diagnostics: (DiagnosticEvent) -> Unit = {},
) : VpnActions {
    private fun record(kind: DiagnosticKind, method: VpnMethod? = null, outcome: DiagnosticOutcome? = null,
        failure: DiagnosticFailure? = null, duration: Long? = null, country: String? = null) {
        runCatching { diagnostics(DiagnosticEvent(java.time.Instant.now().toString(), elapsedMillis(), kind,
            method = method?.id, outcome = outcome, failure = failure, duration_ms = duration?.coerceAtLeast(0), country = country)) }
    }
    private val mutable = MutableStateFlow(VpnStatus())
    override val status = mutable.asStateFlow()
    private var operation: Job? = null
    private var stopping: Job? = null
    private var active: ConnectionAdapter? = null
    private var remoteCleanupPending = false
    private var startupRecovery: Job? = null
    private var recoveredOwner: String? = null
    private var restart: Job? = null
    private var resetRequested = false
    private var intentRevision = 0L
    private val healthWake = Channel<Unit>(Channel.CONFLATED)

    override fun connect(country: String) {
        if (operation?.isActive == true || stopping?.isActive == true || (active != null && !remoteCleanupPending)) return
        if (country != "AUTO" && !country.matches(Regex("[A-Z]{2}"))) return
        val id = owner() ?: return
        record(DiagnosticKind.VPN_CONNECT, country = country)
        intentRevision++
        operation = scope.launch {
            val recoveries = ArrayDeque<Long>()
            try {
                if (startupRecovery?.isActive == true || remoteCleanupPending || (recovery != null && recoveredOwner != id)) {
                    mutable.value = VpnStatus(VpnPhase.CONNECTING)
                }
                startupRecovery?.join()
                if (owner() != id) { mutable.value = VpnStatus(); return@launch }
                if (remoteCleanupPending) finishCleanup()
                if (recovery != null && recoveredOwner != id) {
                    try { recoverStartup(id) }
                    catch (cancel: CancellationException) { throw cancel }
                    catch (_: Exception) {
                        mutable.value = VpnStatus(error = VpnError.CLEANUP)
                        return@launch
                    }
                }
                while (true) {
                    ensureActive()
                    if (owner() != id) { mutable.value = VpnStatus(); return@launch }
                    var previous: VpnMethod? = null
                    val selected = enabledMethods()
                    val allowed = if (selected == null) adapters else selected.distinct().mapNotNull { method -> adapters.find { it.method.id == method } }
                    val priority = preference.order(allowed.map { it.method.id }.distinct())
                    val ordered = allowed.sortedBy { priority.indexOf(it.method.id) }
                    var connectedAdapter: ConnectionAdapter? = null
                    for (adapter in ordered) {
                        ensureActive()
                        if (owner() != id) { mutable.value = VpnStatus(); return@launch }
                        mutable.value = VpnStatus(VpnPhase.CONNECTING, attempt = VpnAttempt(adapter.method, previous))
                        var connected = false
                        var terminalError: VpnError? = null
                        val started = elapsedMillis()
                        var outcome = DiagnosticOutcome.FAILED
                        var failure: DiagnosticFailure? = null
                        record(DiagnosticKind.VPN_ATTEMPT, adapter.method, DiagnosticOutcome.STARTED)
                        try {
                            val result = adapter.connect(country)
                            ensureActive()
                            if (owner() == id && result == ConnectionResult.Verified) {
                                active = adapter; connected = true; connectedAdapter = adapter
                                preference.remember(adapter.method.id)
                                outcome = DiagnosticOutcome.SUCCESS
                                mutable.value = VpnStatus(VpnPhase.CONNECTED, method = adapter.method, egress = adapter.egress)
                            }
                        } catch (e: CancellationException) { outcome = DiagnosticOutcome.CANCELLED; failure = diagnosticFailure(e); throw e }
                        catch (error: AuthFailure) {
                            failure = diagnosticFailure(error)
                            terminalError = when (error.code) {
                                "DEMO_QUOTA_EXHAUSTED" -> VpnError.DEMO_LIMIT
                                "FREE_QUOTA_EXHAUSTED", "FREE_DAILY_LIMIT_REACHED" -> VpnError.FREE_LIMIT
                                "REGISTRATION_REQUIRED", "FREE_QUOTA_RESERVED" -> VpnError.ACCESS
                                else -> null
                            }
                        }
                        catch (error: Exception) { failure = diagnosticFailure(error) /* Continue only after completed cleanup. */ }
                        finally {
                            record(DiagnosticKind.VPN_RESULT, adapter.method, outcome, failure, elapsedMillis() - started)
                            if (!connected) withContext(NonCancellable) {
                            try { adapter.disconnect() } catch (error: Exception) { active = adapter; throw error }
                        } }
                        if (terminalError != null) {
                            mutable.value = VpnStatus(VpnPhase.FAILED, terminalError)
                            return@launch
                        }
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
                    finishCleanup(retryNetwork = broken)
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
            catch (error: Exception) { reportCleanupFailure(error) }
        }
    }
    private suspend fun finishCleanup(retryNetwork: Boolean = false) {
        try {
            withContext(NonCancellable) { active?.disconnect() }
        } catch (error: RemoteCleanupFailure) {
            remoteCleanupPending = true
            if (!retryNetwork) throw error
            // Local shutdown succeeded. Retry the idempotent lease revocation
            // while the system's default network settles.
            readWithNetworkGrace(now = elapsedMillis) {
                try { withContext(NonCancellable) { active?.disconnect() } }
                catch (retry: RemoteCleanupFailure) { throw (retry.cause as? AuthFailure ?: retry) }
            }
        }
        active = null
        remoteCleanupPending = false
    }
    private fun reportCleanupFailure(error: Exception) {
        if (error is RemoteCleanupFailure) remoteCleanupPending = true
        mutable.value = if (remoteCleanupPending) VpnStatus(error = VpnError.CLEANUP)
            else VpnStatus(VpnPhase.FAILED, VpnError.CLEANUP)
    }
    override fun disconnect() {
        record(DiagnosticKind.VPN_DISCONNECT, active?.method)
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
            startupRecovery?.join()
            try {
                finishCleanup()
                mutable.value = VpnStatus(if (resetRequested) VpnPhase.RECONNECTING else VpnPhase.DISCONNECTED)
            } catch (cancel: CancellationException) { throw cancel }
            catch (error: Exception) { reportCleanupFailure(error) }
        }
    }
    override fun resetMethods(country: String) {
        if (country != "AUTO" && !country.matches(Regex("[A-Z]{2}"))) return
        val id = owner() ?: return
        record(DiagnosticKind.VPN_RESET, country = country)
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
        record(DiagnosticKind.VPN_TRANSPORT_LOST, adapters.firstOrNull { it.method.id == method }?.method)
        if (healthPolicy != null && active?.method?.id == method && stopping?.isActive != true &&
            mutable.value.phase in setOf(VpnPhase.CONNECTED, VpnPhase.CHECKING, VpnPhase.WAITING_NETWORK)) {
            mutable.value = VpnStatus(VpnPhase.CHECKING, method = active?.method)
            healthWake.trySend(Unit)
        }
    }
    fun checkAfterWake() {
        if (active != null && operation?.isActive == true &&
            mutable.value.phase in setOf(VpnPhase.CONNECTED, VpnPhase.CHECKING, VpnPhase.WAITING_NETWORK)) {
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
            val started = elapsedMillis()
            var failure: DiagnosticFailure? = null
            val health = try { adapter.health() }
                catch (cancel: CancellationException) { throw cancel }
                catch (error: Exception) { failure = diagnosticFailure(error); TunnelHealth.UNKNOWN }
            record(DiagnosticKind.VPN_HEALTH, adapter.method, DiagnosticOutcome.valueOf(health.name), failure, elapsedMillis() - started)
            currentCoroutineContext().ensureActive()
            if (owner() != id) return false
            when (health) {
                TunnelHealth.SUSPENDED -> { failures = 0 } // Doze forbids probes; retain the last real state.
                TunnelHealth.HEALTHY -> { failures = 0; mutable.value = VpnStatus(VpnPhase.CONNECTED, method = adapter.method, egress = adapter.egress) }
                TunnelHealth.NO_NETWORK -> { failures = 0; mutable.value = VpnStatus(VpnPhase.WAITING_NETWORK, method = adapter.method) }
                TunnelHealth.UNKNOWN -> { failures = 0; mutable.value = VpnStatus(VpnPhase.CHECKING, method = adapter.method) }
                TunnelHealth.UNREACHABLE -> {
                    failures++
                    mutable.value = VpnStatus(VpnPhase.CHECKING, method = adapter.method)
                    if (failures >= policy.failureThreshold) return true
                }
            }
            wait = if (health in setOf(TunnelHealth.HEALTHY, TunnelHealth.UNKNOWN, TunnelHealth.SUSPENDED)) policy.intervalMillis else policy.retryMillis
        }
    }
    suspend fun beforeLogout() { disconnect(); stopping?.join() }
    suspend fun beforeForget() = beforeLogout()
    suspend fun confirmedDeviceRevocation() = beforeLogout()
    fun recover() {
        val id = owner() ?: return
        if (recovery == null || recoveredOwner == id || startupRecovery?.isActive == true ||
            active != null || operation?.isActive == true || stopping?.isActive == true) return
        startupRecovery = scope.launch {
            try { recoverStartup(id) }
            catch (error: CancellationException) { throw error }
            catch (_: Exception) { /* An explicit Connect can retry before creating a new lease. */ }
        }
    }
    private suspend fun recoverStartup(id: String) {
        record(DiagnosticKind.VPN_RECOVER, outcome = DiagnosticOutcome.STARTED)
        recovery?.recover()
        recoveredOwner = id
    }
}
