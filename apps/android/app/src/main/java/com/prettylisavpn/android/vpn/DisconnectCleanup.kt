package com.prettylisavpn.android.vpn

import kotlinx.coroutines.CancellationException

internal class RemoteCleanupFailure(cause: Exception) : IllegalStateException("VPN_REMOTE_CLEANUP_FAILED", cause)

/** A local stop failure must not leave a renewable server grant behind. */
internal suspend fun disconnectCleanup(
    stopLocal: suspend () -> Unit,
    revokeRemote: suspend () -> Unit,
    onLocalStopped: () -> Unit = {},
) {
    var localFailure: Exception? = null
    try { stopLocal() } catch (error: Exception) { localFailure = error }
    if (localFailure == null) onLocalStopped()
    try { vpnDeadline(35_000) { revokeRemote() } }
    catch (cancel: CancellationException) { throw cancel }
    catch (error: Exception) {
        if (localFailure == null) throw RemoteCleanupFailure(error)
        if (localFailure !== error) localFailure.addSuppressed(error)
    }
    localFailure?.let { throw it }
}
