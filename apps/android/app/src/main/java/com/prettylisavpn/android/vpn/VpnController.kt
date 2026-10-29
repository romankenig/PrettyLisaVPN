package com.prettylisavpn.android.vpn

import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow

enum class VpnPhase { DISCONNECTED, CONNECTING, CONNECTED, DISCONNECTING, FAILED }
enum class VpnError { METHODS_EXHAUSTED, CLEANUP, ACCESS }
data class VpnAttempt(val method: VpnMethod, val previousMethod: VpnMethod? = null)
data class VpnStatus(val phase: VpnPhase = VpnPhase.DISCONNECTED, val error: VpnError? = null,
    val method: VpnMethod? = null, val attempt: VpnAttempt? = null)
interface VpnActions {
    val status: kotlinx.coroutines.flow.StateFlow<VpnStatus>
    fun connect(country: String)
    fun disconnect()
}

/** One executor for verified adapters; cleanup fences every fallback attempt. */
class VpnController(
    private val owner: () -> String?,
    private val scope: CoroutineScope,
    private val adapters: List<ConnectionAdapter>,
    private val preference: MethodPreference = MethodPreference(),
    private val recovery: ConnectionAdapter? = null,
    private val enabledMethods: () -> Set<String>? = { null },
) : VpnActions {
    private val mutable = MutableStateFlow(VpnStatus())
    override val status = mutable.asStateFlow()
    private var operation: Job? = null
    private var stopping: Job? = null
    private var active: ConnectionAdapter? = null
    private var recoveredOwner: String? = null

    override fun connect(country: String) {
        if (operation?.isActive == true || stopping?.isActive == true || active != null) return
        if (country != "AUTO" && !country.matches(Regex("[A-Z]{2}"))) return
        val id = owner() ?: return
        operation = scope.launch {
            var previous: VpnMethod? = null
            try {
                val preferred = preference.current()
                val selected = enabledMethods()
                val allowed = adapters.filter { selected == null || it.method.id in selected }
                val ordered = allowed.filter { it.method.id == preferred } + allowed.filter { it.method.id != preferred }
                for (adapter in ordered) {
                    ensureActive()
                    if (owner() != id) { mutable.value = VpnStatus(); return@launch }
                    mutable.value = VpnStatus(VpnPhase.CONNECTING, attempt = VpnAttempt(adapter.method, previous))
                    var connected = false
                    try {
                        val result = adapter.connect(country)
                        ensureActive()
                        if (owner() == id && result == ConnectionResult.Verified) {
                            active = adapter; connected = true
                            preference.remember(adapter.method.id)
                            mutable.value = VpnStatus(VpnPhase.CONNECTED, method = adapter.method)
                            return@launch
                        }
                    } catch (e: CancellationException) { throw e }
                    catch (_: Exception) { /* Continue only after completed cleanup. */ }
                    finally { if (!connected) withContext(NonCancellable) {
                        try { adapter.disconnect() } catch (error: Exception) { active = adapter; throw error }
                    } }
                    previous = adapter.method
                }
                mutable.value = VpnStatus(VpnPhase.FAILED, VpnError.METHODS_EXHAUSTED, method = previous)
            } catch (e: CancellationException) { throw e }
            catch (_: Exception) { mutable.value = VpnStatus(VpnPhase.FAILED, VpnError.CLEANUP) }
        }
    }
    override fun disconnect() {
        if (stopping?.isActive == true) return
        operation?.cancel()
        mutable.value = VpnStatus(VpnPhase.DISCONNECTING)
        stopping = scope.launch {
            operation?.join()
            try {
                active?.disconnect(); active = null
                mutable.value = VpnStatus()
            } catch (_: Exception) { mutable.value = VpnStatus(VpnPhase.FAILED, VpnError.CLEANUP) }
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
