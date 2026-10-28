package com.prettylisavpn.android.vpn

/** A local stop failure must not leave a renewable server grant behind. */
internal suspend fun disconnectCleanup(stopLocal: suspend () -> Unit, revokeRemote: suspend () -> Unit) {
    var failure: Exception? = null
    try { stopLocal() } catch (error: Exception) { failure = error }
    try { revokeRemote() } catch (error: Exception) {
        failure?.let(error::addSuppressed)
        throw error
    }
    failure?.let { throw it }
}
