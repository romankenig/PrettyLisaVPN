package com.prettylisavpn.android.auth

import java.time.Instant
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

interface CredentialVault {
    fun read(): Credentials?
    fun write(credentials: Credentials)
    fun clear()
    fun installationId(): String
}

/** One process-wide owner. All refresh/login/logout transitions share this mutex.
 * The durable pending marker prevents replay after a timeout or death during rotation.
 */
class SessionCoordinator(
    private val api: AuthApi,
    private val vault: CredentialVault,
    private val deviceName: String,
    private val now: () -> Instant = { Instant.now() },
    private val elapsedMillis: () -> Long = { System.nanoTime() / 1_000_000 },
) {
    private val mutex = Mutex()
    private var access: String? = null
    private var accessUntil = 0L
    var profile: Profile? = null
        private set
    var needsRecovery = false
        private set
    private val terminal = setOf("invalid_refresh_token", "invalid_session", "device_revoked", "user_blocked", "authentication_required")
    private suspend fun storage(block: () -> Unit) { try { withContext(Dispatchers.IO) { block() } } catch (failure: CancellationException) { throw failure } catch (_: Exception) { access = null; profile = null; throw AuthFailure("storage_unavailable") } }
    private suspend fun credentials(): Credentials? = try { withContext(Dispatchers.IO) { vault.read() } } catch (failure: CancellationException) { throw failure } catch (_: Exception) { throw AuthFailure("storage_unavailable") }
    private suspend fun clear() { access = null; profile = null; storage { vault.clear() }; needsRecovery = false }
    suspend fun requestOtp(email: String) = mutex.withLock { api.requestOtp(email) }
    suspend fun login(email: String, code: String): Profile = mutex.withLock {
        val installation = try { withContext(Dispatchers.IO) { vault.installationId() } } catch (failure: CancellationException) { throw failure } catch (_: Exception) { throw AuthFailure("storage_unavailable") }
        val tokens = api.verifyOtp(email, code, installation, deviceName)
        accept(tokens)
        fetchProfile()
    }
    private suspend fun accept(tokens: Tokens) {
        // Persist the new refresh credential BEFORE using its bearer or publishing authentication.
        needsRecovery = true
        storage { vault.write(tokens.credentials) }
        access = tokens.access
        accessUntil = elapsedMillis() + (tokens.ttlSeconds.coerceAtMost(86_400) * 1_000 - 5_000).coerceAtLeast(0)
    }
    private suspend fun bearer(): String {
        access?.takeIf { elapsedMillis() < accessUntil }?.let { return it }
        val stored = credentials() ?: throw AuthFailure("reauth_required")
        if (!Instant.parse(stored.expiresAt).isAfter(now())) { clear(); throw AuthFailure("reauth_required") }
        if (stored.rotationPending) { access = null; profile = null; throw AuthFailure("rotation_uncertain") }
        storage { vault.write(stored.copy(rotationPending = true)) }
        val tokens = try { api.refresh(stored) } catch (failure: AuthFailure) {
            access = null
            if (failure.code in terminal) { clear(); throw failure }
            // These outcomes prove no successful rotation. All ambiguous outcomes retain the marker.
            if (failure.code in setOf("offline", "service_unavailable")) storage { vault.write(stored) }
            throw failure
        }
        if (tokens.credentials.sessionId != stored.sessionId) throw AuthFailure("rotation_uncertain")
        accept(tokens)
        return tokens.access
    }
    private suspend fun <T> authenticated(action: suspend (String) -> T): T {
        try {
            val token = bearer()
            return try { action(token) } catch (failure: AuthFailure) {
                if (failure.code != "invalid_access_token") throw failure
                access = null
                action(bearer()) // One bounded refresh/retry, never an interceptor replay of POST refresh.
            }
        } catch (failure: AuthFailure) {
            if (failure.code in terminal || failure.code == "invalid_access_token") clear()
            throw failure
        }
    }
    private suspend fun fetchProfile(): Profile = authenticated { api.me(it) }.also { profile = it; needsRecovery = false }
    suspend fun restore(): Profile? = mutex.withLock {
        if (credentials() == null) { access = null; profile = null; null } else fetchProfile()
    }
    suspend fun <T> request(action: suspend (String) -> T): T = mutex.withLock { authenticated(action) }
    suspend fun refreshProfile(): Profile = mutex.withLock { fetchProfile() }
    suspend fun logout() = mutex.withLock {
        try { authenticated { api.logout(it) } } catch (failure: AuthFailure) {
            // A confirmed unusable session is already signed out. Offline/timeout retain credentials.
            if (failure.code !in terminal && failure.code != "invalid_access_token" && failure.code != "reauth_required") throw failure
        }
        clear()
    }
    /** Explicit user action only; does not claim a remote logout. */
    suspend fun forgetLocalSession() = mutex.withLock { clear() }
}
