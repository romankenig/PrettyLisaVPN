package com.prettylisavpn.android.data

import androidx.lifecycle.ViewModel
import com.prettylisavpn.android.auth.AuthFailure
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow

enum class LoadPhase { IDLE, LOADING, READY, ERROR }
data class Load(val phase: LoadPhase = LoadPhase.IDLE, val error: String? = null)
data class ScreenState(val data: Snapshot, val loads: Map<Area, Load> = emptyMap(), val busy: Boolean = false, val error: String? = null)

/** Activity ViewModel owns operations, so rotation never repeats a mutation. Process death resets fixtures. */
class ScreenModel(private val source: ScreenSource) : ViewModel() {
    val enabled = source.enabled
    val fixture = source.fixture
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val mutable = MutableStateFlow(ScreenState(source.initial))
    val state = mutable.asStateFlow()
    private var epoch = 0
    var emailDraft = ""
    var resendAtMillis = 0L
        private set
    init { if (!fixture) load(Area.SESSION) }
    fun load(area: Area) {
        if (!enabled || mutable.value.loads[area]?.phase == LoadPhase.LOADING) return
        val owner = epoch
        mutable.value = mutable.value.copy(loads = mutable.value.loads + (area to Load(LoadPhase.LOADING)))
        scope.launch {
            try {
                val data = source.read(area)
                if (owner == epoch) mutable.value = mutable.value.copy(data = data, loads = mutable.value.loads + (area to Load(LoadPhase.READY)))
            } catch (failure: Exception) {
                if (failure is CancellationException) throw failure
                if (owner == epoch) {
                    val data = if (fixture) mutable.value.data else source.initial
                    val ended = !fixture && failure is AuthFailure && failure.code in setOf("reauth_required", "invalid_refresh_token", "invalid_session", "device_revoked", "user_blocked")
                    mutable.value = mutable.value.copy(data = data,
                        error = if (!fixture && !data.signedIn) failure.message else mutable.value.error,
                        loads = mutable.value.loads + (area to Load(if (ended) LoadPhase.READY else LoadPhase.ERROR, failure.message)))
                }
            }
        }
    }
    fun perform(command: Command, onSuccess: () -> Unit = {}) {
        if (!enabled || mutable.value.busy) return
        val owner = epoch
        mutable.value = mutable.value.copy(busy = true, error = null)
        scope.launch {
            try {
                val data = source.execute(command)
                if (owner == epoch) {
                    if (!data.signedIn && mutable.value.data.signedIn) epoch++
                    mutable.value = mutable.value.copy(data = data, busy = false, error = null)
                    if (command is Command.RequestOtp) resendAtMillis = android.os.SystemClock.elapsedRealtime() + 30_000
                    onSuccess()
                }
            } catch (failure: Exception) {
                if (failure is CancellationException) throw failure
                if (owner == epoch) {
                    mutable.value = mutable.value.copy(data = if (fixture) mutable.value.data else source.initial, busy = false, error = failure.message ?: "Service unavailable.")
                    if (source.recoveryRequired) mutable.value = mutable.value.copy(loads = mutable.value.loads + (Area.SESSION to Load(LoadPhase.ERROR, failure.message)))
                }
            }
        }
    }
    fun clearError() { mutable.value = mutable.value.copy(error = null) }
    fun configure(scenario: Scenario) {
        if (mutable.value.busy) return
        if (scenario == Scenario.FAIL_NEXT) {
            source.configure(scenario)
            clearError()
            return
        }
        epoch++
        source.configure(scenario)
        mutable.value = ScreenState(source.initial)
    }
    override fun onCleared() { scope.cancel() }
}
