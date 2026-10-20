package com.prettylisavpn.android.auth

import java.time.Instant
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test

class MemoryVault : CredentialVault {
    var value: Credentials? = null
    var failWrite = false
    val history = mutableListOf<Credentials>()
    override fun read() = value
    override fun write(credentials: Credentials) { check(!failWrite); value = credentials; history += credentials }
    override fun clear() { value = null }
    override fun installationId() = "a1d3475f-0155-49e9-88a9-27125a19b12d"
}
class FakeApi : AuthApi {
    val issued = Tokens("access-1", 60, Credentials("c21132ac-0d2e-4da7-96ac-8a6ceeb019ba", "refresh-1", "2030-01-01T00:00:00Z"))
    var refreshes = 0
    var verifies = 0
    var logouts = 0
    var error: String? = null
    var refreshError: String? = null
    var meError: String? = null
    var rejectAccessOnce = false
    var beforeMe: (() -> Unit)? = null
    override suspend fun requestOtp(email: String) { error?.let { throw AuthFailure(it) } }
    override suspend fun verifyOtp(email: String, code: String, installationId: String, deviceName: String): Tokens {
        verifies++; error?.let { throw AuthFailure(it) }; return issued
    }
    override suspend fun refresh(credentials: Credentials): Tokens {
        refreshes++; delay(10); refreshError?.let { throw AuthFailure(it) }
        return issued.copy(access = "access-${refreshes+1}", credentials = issued.credentials.copy(refreshToken = "refresh-${refreshes+1}"))
    }
    override suspend fun me(access: String): Profile {
        beforeMe?.invoke()
        if (rejectAccessOnce) { rejectAccessOnce = false; throw AuthFailure("invalid_access_token") }
        (meError ?: error)?.let { throw AuthFailure(it) }
        return Profile("person@example.com", "Premium", 2)
    }
    override suspend fun logout(access: String) { logouts++; error?.let { throw AuthFailure(it) } }
}
class SessionCoordinatorTest {
    private val vault = MemoryVault()
    private val api = FakeApi()
    private var elapsed = 0L
    private var clock = Instant.parse("2026-10-20T00:00:00Z")
    private fun coordinator() = SessionCoordinator(api, vault, "Android test", { clock }, { elapsed })
    private suspend fun expect(code: String, action: suspend () -> Unit) {
        try { action(); fail("Expected $code") } catch (e: AuthFailure) { assertEquals(code, e.code) }
    }
    @Test fun loginPersistsBeforeMeAndDoesNotStoreBearer() = runBlocking {
        api.beforeMe = { assertEquals(api.issued.credentials, vault.value) }
        assertEquals("person@example.com", coordinator().login("person@example.com", "123456").email)
        assertEquals(0, api.refreshes)
    }
    @Test fun freshInstallDoesNotCallNetwork() = runBlocking { assertNull(coordinator().restore()); assertEquals(0, api.refreshes) }
    @Test fun restartRotatesAndAtomicallyReplacesCredential() = runBlocking {
        coordinator().login("person@example.com", "123456")
        assertNotNull(coordinator().restore())
        assertEquals("refresh-2", vault.value!!.refreshToken)
        assertFalse(vault.value!!.rotationPending)
        assertTrue(vault.history.any { it.rotationPending })
    }
    @Test fun concurrentExpiredRequestsHaveOneRotation() = runBlocking {
        val sessions = coordinator(); sessions.login("person@example.com", "123456"); elapsed = 60_000
        coroutineScope { (1..20).map { async { sessions.refreshProfile() } }.awaitAll() }
        assertEquals(1, api.refreshes)
    }
    @Test fun unauthorizedBearerRefreshesOnlyOnce() = runBlocking {
        val sessions = coordinator(); sessions.login("person@example.com", "123456"); api.rejectAccessOnce = true
        sessions.refreshProfile(); assertEquals(1, api.refreshes)
    }
    @Test fun refreshExpiryClearsWithoutNetwork() = runBlocking {
        vault.value = api.issued.credentials; clock = Instant.parse("2031-01-01T00:00:00Z")
        expect("reauth_required") { coordinator().restore() }; assertNull(vault.value); assertEquals(0, api.refreshes)
    }
    @Test fun invalidRefreshClearsSession() = runBlocking {
        vault.value = api.issued.credentials; api.refreshError = "invalid_refresh_token"
        expect("invalid_refresh_token") { coordinator().restore() }; assertNull(vault.value)
    }
    @Test fun deviceRevocationOnMeClearsMemoryAndDisk() = runBlocking {
        val sessions = coordinator(); sessions.login("person@example.com", "123456"); api.meError = "device_revoked"
        expect("device_revoked") { sessions.refreshProfile() }; assertNull(sessions.profile); assertNull(vault.value)
    }
    @Test fun deviceRevocationOnRefreshClearsDisk() = runBlocking {
        vault.value = api.issued.credentials; api.refreshError = "device_revoked"
        expect("device_revoked") { coordinator().restore() }; assertNull(vault.value)
    }
    @Test fun blockedAccountClearsSession() = runBlocking {
        val sessions = coordinator(); sessions.login("person@example.com", "123456"); api.error = "user_blocked"
        expect("user_blocked") { sessions.refreshProfile() }; assertNull(vault.value)
    }
    @Test fun offlineRestoreRetainsCredentialsAndCanRetry() = runBlocking {
        vault.value = api.issued.credentials; api.refreshError = "offline"; val sessions = coordinator()
        expect("offline") { sessions.restore() }; assertEquals(api.issued.credentials, vault.value)
        api.refreshError = null; assertNotNull(sessions.restore())
    }
    @Test fun serviceUnavailableCanRetryRotation() = runBlocking {
        vault.value = api.issued.credentials; api.refreshError = "service_unavailable"
        expect("service_unavailable") { coordinator().restore() }; assertFalse(vault.value!!.rotationPending)
    }
    @Test fun lostRefreshResponseIsNotReplayedAfterRestart() = runBlocking {
        vault.value = api.issued.credentials; api.refreshError = "network_uncertain"
        expect("network_uncertain") { coordinator().restore() }; assertTrue(vault.value!!.rotationPending)
        api.refreshError = null
        expect("rotation_uncertain") { coordinator().restore() }; assertEquals(1, api.refreshes)
    }
    @Test fun processDeathDuringRotationRequiresNewLogin() = runBlocking {
        vault.value = api.issued.credentials.copy(rotationPending = true)
        expect("rotation_uncertain") { coordinator().restore() }; assertEquals(0, api.refreshes)
    }
    @Test fun failedSecureWriteNeverPublishesAuthentication() = runBlocking {
        vault.failWrite = true; val sessions = coordinator()
        expect("storage_unavailable") { sessions.login("person@example.com", "123456") }
        assertNull(sessions.profile)
    }
    @Test fun failedRotationWriteDoesNotSendToken() = runBlocking {
        vault.value = api.issued.credentials; vault.failWrite = true
        expect("storage_unavailable") { coordinator().restore() }; assertEquals(0, api.refreshes)
    }
    @Test fun logoutSuccessClearsBothTokens() = runBlocking {
        val sessions = coordinator(); sessions.login("person@example.com", "123456"); sessions.logout()
        assertNull(vault.value); assertNull(sessions.profile); assertEquals(1, api.logouts)
    }
    @Test fun offlineLogoutRetainsSessionAndReportsFailure() = runBlocking {
        val sessions = coordinator(); sessions.login("person@example.com", "123456"); api.error = "offline"
        expect("offline") { sessions.logout() }; assertNotNull(vault.value); assertNotNull(sessions.profile)
        api.error = null; sessions.logout(); assertNull(vault.value)
    }
    @Test fun ambiguousLogoutCanReconcileInvalidSession() = runBlocking {
        val sessions = coordinator(); sessions.login("person@example.com", "123456"); api.error = "network_uncertain"
        expect("network_uncertain") { sessions.logout() }; assertNotNull(vault.value)
        api.error = "invalid_session"; sessions.logout(); assertNull(vault.value)
    }
    @Test fun logoutAndRefreshCannotResurrectAccount() = runBlocking {
        val sessions = coordinator(); sessions.login("person@example.com", "123456"); elapsed = 60_000
        coroutineScope { val refresh = async { sessions.refreshProfile() }; yield(); val logout = async { sessions.logout() }; refresh.await(); logout.await() }
        assertNull(sessions.profile); assertNull(vault.value)
    }
    @Test fun invalidOtpDoesNotPersistCredentials() = runBlocking {
        api.error = "otp_invalid_or_expired"
        expect("otp_invalid_or_expired") { coordinator().login("person@example.com", "000000") }; assertNull(vault.value)
    }
    @Test fun acceptedOtpWithOfflineProfileCanRecoverWithoutReusingCode() = runBlocking {
        val sessions = coordinator(); api.meError = "offline"
        expect("offline") { sessions.login("person@example.com", "123456") }
        assertTrue(sessions.needsRecovery); assertNotNull(vault.value)
        api.meError = null; sessions.restore()
        assertFalse(sessions.needsRecovery); assertEquals(1, api.verifies)
    }
    @Test fun localForgetNeverClaimsRemoteLogout() = runBlocking {
        val sessions = coordinator(); sessions.login("person@example.com", "123456"); sessions.forgetLocalSession()
        assertNull(vault.value); assertEquals(0, api.logouts)
    }
}
