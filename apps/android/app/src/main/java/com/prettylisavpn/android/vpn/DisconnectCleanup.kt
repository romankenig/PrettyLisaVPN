package com.prettylisavpn.android.vpn

import kotlinx.coroutines.CancellationException

internal class RemoteCleanupFailure(cause: Exception) : IllegalStateException("VPN_REMOTE_CLEANUP_PENDING", cause)

/** A local stop failure must not leave a renewable server grant behind. */
internal suspend fun disconnectCleanup(stopLocal: suspend () -> Unit, revokeRemote: suspend () -> Unit) {
    val localFailure = try { stopLocal(); null } catch (error: Exception) { error }
    try {
        revokeRemote()
    } catch (error: CancellationException) {
        throw error
    } catch (error: Exception) {
        if (localFailure == null) throw RemoteCleanupFailure(error)
        localFailure.addSuppressed(error)
    }
    localFailure?.let { throw it }
}
