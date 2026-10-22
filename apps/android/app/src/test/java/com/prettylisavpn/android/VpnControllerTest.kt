package com.prettylisavpn.android

import com.prettylisavpn.android.auth.AuthFailure
import com.prettylisavpn.android.vpn.*
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test
import java.time.Instant

class VpnControllerTest {
    private val sessionId = "d84cd4d2-8aee-4c17-9772-31db1d512924"
    private val config = VpnConfig("203.0.113.1", 51820, "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE=", "10.77.0.2/32", listOf("1.1.1.1"))
    private fun session(compatible: Boolean = true) = VpnSession(sessionId, "DE", Instant.now(), null, if (compatible) config else null)
    private class Store : VpnJournal {
        var pending: PendingVpn? = null
        var fail = false
        var writes = 0; var failAt = -1
        override fun read(owner: String) = pending
        override fun write(owner: String, value: PendingVpn?) { writes++; if (fail || writes == failAt) error("disk"); pending = value }
    }
    private inner class Api : VpnApi {
        var value: VpnSession? = null
        var posts = 0; var deletes = 0; var failDelete = false; var failCreate: String? = null
        var compatible = true
        var allocated: VpnSession? = null
        var gate: CompletableDeferred<Unit>? = null
        override suspend fun current() = value
        override suspend fun create(country: String, publicKey: String): VpnSession {
            posts++; gate?.await()
            failCreate?.let { throw AuthFailure(it) }
            return (allocated ?: session(compatible)).also { value = it }
        }
        override suspend fun delete(id: String) { deletes++; if (failDelete) throw AuthFailure("offline"); value = null }
    }
    private class Runtime : TunnelRuntime {
        var timeout = false; var failStop = false
        var up = false; var starts = 0; var stops = 0; var verified = true; var failStart = false
        override suspend fun start(config: VpnConfig, key: TunnelKey) { starts++; if (failStart) error("native"); up = true }
        override suspend fun stop() { stops++; if(failStop) error("stop failed"); up = false }
        override suspend fun verify(config: VpnConfig): Boolean { if(timeout) withTimeout(1) { delay(100) }; return up && verified }
    }
    private suspend fun await(predicate: () -> Boolean) = withTimeout(5_000) { while (!predicate()) delay(5) }
    private fun controller(api: Api, runtime: Runtime, store: Store, scope: CoroutineScope, owner: () -> String? = { "owner" }, clock: () -> Long = { System.nanoTime()/1_000_000 }) = VpnController(api, runtime, store, owner,
        { object : TunnelKey { override val publicKey = config.serverKey } }, scope, clock, monitorMillis = 25)
    private fun scenario(block: suspend CoroutineScope.() -> Unit) = runBlocking {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
        try { scope.block() } finally { scope.cancel() }
    }
    @Test fun connectedRequiresVerificationAndDisconnectRemovesPeer() = scenario {
        val api = Api(); val runtime = Runtime(); val store = Store(); runtime.verified = false
        val c = controller(api, runtime, store, this)
        c.connect("DE"); await { c.status.value.phase == VpnPhase.VERIFYING }
        assertFalse(c.status.value.phase == VpnPhase.CONNECTED)
        runtime.verified = true; await { c.status.value.phase == VpnPhase.CONNECTED }
        c.disconnect(); await { c.status.value.phase == VpnPhase.DISCONNECTED }
        assertEquals(1, api.posts); assertTrue(api.deletes >= 1); assertFalse(runtime.up); assertNull(store.pending)
    }
    @Test fun cancelVerificationThenReconnectDoesNotRaceASecondCleanup() = scenario {
        val api=Api();val runtime=Runtime();val store=Store();runtime.verified=false
        val c=controller(api,runtime,store,this)
        c.connect("AUTO");await { c.status.value.phase==VpnPhase.VERIFYING }
        repeat(3) { c.disconnect() };await { c.status.value.phase==VpnPhase.DISCONNECTED }
        // A UI frame can now offer connect again; there must be no queued cleanup to swallow it.
        delay(10);runtime.verified=true;c.connect("AUTO")
        await { c.status.value.phase==VpnPhase.CONNECTED };assertEquals(2,api.posts);c.beforeLogout()
    }
    @Test fun providerTimeoutCannotSilentlyCancelMonitoringAndLeaveConnected() = scenario {
        val api=Api();val runtime=Runtime();val store=Store();val c=controller(api,runtime,store,this)
        c.connect("AUTO");await { c.status.value.phase==VpnPhase.CONNECTED };runtime.timeout=true
        await { c.status.value.phase==VpnPhase.FAILED }
        assertEquals(VpnError.NETWORK,c.status.value.error);assertFalse(runtime.up);assertNull(api.value)
    }
    @Test fun failedLocalStopKeepsCleanupPendingAndBlocksCredentialRemovalUntilRetry() = scenario {
        val api=Api();val runtime=Runtime();val store=Store();val c=controller(api,runtime,store,this)
        c.connect("AUTO");await { c.status.value.phase==VpnPhase.CONNECTED };runtime.failStop=true
        c.disconnect();await { c.status.value.phase==VpnPhase.CLEANUP_PENDING }
        assertTrue(runtime.up);assertNotNull(store.pending);assertEquals(0,api.deletes)
        try { c.beforeForget();fail() } catch(e:VpnFailure) { assertEquals(VpnError.CLEANUP,e.reason) }
        runtime.failStop=false;c.beforeLogout()
        assertFalse(runtime.up);assertNull(api.value);assertNull(store.pending)
    }
    @Test fun concurrentClicksCannotCreateTwoSessions() = scenario {
        val api = Api(); val runtime = Runtime(); val store = Store(); api.gate = CompletableDeferred()
        val c = controller(api, runtime, store, this)
        c.connect("AUTO"); c.connect("DE"); await { api.posts == 1 }; assertTrue(store.pending!!.uncertain)
        api.gate!!.complete(Unit); await { c.status.value.phase == VpnPhase.CONNECTED }
        assertEquals(1, api.posts); c.beforeLogout(); assertFalse(runtime.up)
    }
    @Test fun unsupportedProfileIsDeletedWithoutStartingNative() = scenario {
        val api = Api(); api.compatible = false; val runtime = Runtime(); val store = Store()
        val c = controller(api, runtime, store, this); c.connect("AUTO")
        await { c.status.value.phase == VpnPhase.FAILED }
        assertEquals(VpnError.UNSUPPORTED, c.status.value.error); assertEquals(0, runtime.starts); assertNull(api.value); assertNull(store.pending)
    }
    @Test fun nativeStartupFailureCleansServerSession() = scenario {
        val api = Api(); val runtime = Runtime(); runtime.failStart = true; val store = Store()
        val c = controller(api, runtime, store, this); c.connect("AUTO")
        await { c.status.value.phase == VpnPhase.FAILED }; assertNull(api.value); assertFalse(runtime.up); assertNull(store.pending)
    }
    @Test fun failedCleanupIsDurableAndBlocksLogoutUntilRetry() = scenario {
        val api = Api(); val runtime = Runtime(); val store = Store(); val c = controller(api, runtime, store, this)
        c.connect("AUTO"); await { c.status.value.phase == VpnPhase.CONNECTED }; api.failDelete = true
        c.disconnect(); await { c.status.value.phase == VpnPhase.CLEANUP_PENDING }
        assertFalse(runtime.up); assertEquals(sessionId, store.pending!!.id)
        try { c.beforeLogout(); fail() } catch (e: VpnFailure) { assertEquals(VpnError.CLEANUP, e.reason) }
        api.failDelete = false; c.beforeLogout(); assertNull(store.pending); assertNull(api.value)
    }
    @Test fun restartDeletesSavedSessionAndNeverRestoresConnected() = scenario {
        val api = Api(); api.value = session(); val runtime = Runtime(); val store = Store(); store.pending = PendingVpn(sessionId)
        val c = controller(api, runtime, store, this); c.recover()
        assertEquals(VpnPhase.DISCONNECTED, c.status.value.phase); assertEquals(0, api.posts); assertNull(api.value); assertNull(store.pending)
    }
    @Test fun uncertainCreateIsNotReplayedOrForgottenWhenCurrentIsNull() = scenario {
        val api = Api(); api.failCreate = "network_uncertain"; val runtime = Runtime(); val store = Store()
        val c = controller(api, runtime, store, this); c.connect("AUTO")
        await { c.status.value.phase == VpnPhase.CLEANUP_PENDING }; assertTrue(store.pending!!.uncertain)
        c.connect("AUTO"); await { c.status.value.phase == VpnPhase.CLEANUP_PENDING }; delay(100)
        assertEquals(1, api.posts)
        // The original timed-out request eventually becomes visible: cleanup resolves it.
        api.value = session(); c.beforeLogout(); assertNull(api.value); assertNull(store.pending)
    }
    @Test fun cancelWhileCreatingCleansEventualSessionWithoutConnecting() = scenario {
        val api = Api(); api.gate = CompletableDeferred(); val runtime = Runtime(); val store = Store()
        val c = controller(api, runtime, store, this); c.connect("AUTO"); await { api.posts == 1 }; c.disconnect()
        await { c.status.value.phase == VpnPhase.CLEANUP_PENDING }; assertEquals(0, runtime.starts)
        api.value = session(); c.beforeLogout(); assertNull(api.value); assertEquals(1, api.posts)
    }
    @Test fun networkLossNeverLeavesConnectedAndRemovesServerPeer() = scenario {
        val api = Api(); val runtime = Runtime(); val store = Store(); val c = controller(api, runtime, store, this)
        c.connect("AUTO"); await { c.status.value.phase == VpnPhase.CONNECTED }; runtime.verified = false
        await { c.status.value.phase == VpnPhase.FAILED }; assertEquals(VpnError.VERIFICATION, c.status.value.error); assertFalse(runtime.up); assertNull(api.value)
    }
    @Test fun serverRevocationAndDeadlineStopTheTunnel() = scenario {
        val api = Api(); val runtime = Runtime(); val store = Store(); val c = controller(api, runtime, store, this)
        c.connect("AUTO"); await { c.status.value.phase == VpnPhase.CONNECTED }; api.value = null
        await { c.status.value.phase == VpnPhase.FAILED }; assertFalse(runtime.up); assertEquals(VpnError.ACCESS, c.status.value.error)
    }
    @Test fun storageFailurePreventsPostAndOwnerChangeCannotDeleteAnotherAccountsSession() = scenario {
        val api = Api(); val runtime = Runtime(); val store = Store(); store.fail = true
        val c = controller(api, runtime, store, this); c.connect("AUTO"); await { c.status.value.phase == VpnPhase.CLEANUP_PENDING }
        assertEquals(0, api.posts)
        store.fail = false; c.beforeLogout()
        var owner: String? = "first"; val d = controller(api, runtime, store, this, { owner })
        d.connect("AUTO"); await { d.status.value.phase == VpnPhase.CONNECTED }; owner = "second"
        await { d.status.value.phase == VpnPhase.CLEANUP_PENDING }; assertFalse(runtime.up); assertEquals(0, api.deletes)
    }
    @Test fun confirmedRejectionClearsIntentAndAllowsANewAttempt() = scenario {
        val runtime = Runtime(); val store = Store()
        val api = Api(); val rejecting = object : VpnApi {
            var reject = true
            override suspend fun current() = api.current()
            override suspend fun delete(id: String) = api.delete(id)
            override suspend fun create(country: String, publicKey: String): VpnSession {
                if (reject) { reject = false; throw VpnCreateRejected(AuthFailure("FREE_DAILY_LIMIT_REACHED")) }
                return api.create(country,publicKey)
            }
        }
        val c = VpnController(rejecting,runtime,store,{ "owner" },{ object : TunnelKey { override val publicKey = config.serverKey } },this,{ System.nanoTime()/1_000_000 })
        c.connect("AUTO"); await { c.status.value.phase == VpnPhase.FAILED }
        assertEquals(VpnError.QUOTA,c.status.value.error); assertNull(store.pending)
        delay(25); c.connect("AUTO"); await { c.status.value.phase == VpnPhase.CONNECTED }; c.beforeLogout()
    }
    @Test fun explicitLocalForgetStopsTunnelButPreservesOfflineCleanupIntent() = scenario {
        val api=Api(); val runtime=Runtime(); val store=Store(); val c=controller(api,runtime,store,this)
        c.connect("AUTO"); await { c.status.value.phase == VpnPhase.CONNECTED }; api.failDelete=true
        c.beforeForget()
        assertFalse(runtime.up); assertEquals(sessionId,store.pending!!.id); assertEquals(VpnPhase.CLEANUP_PENDING,c.status.value.phase)
    }
    @Test fun confirmedDeviceRevocationResolvesUnknownCreateWithoutReplayingPost() = scenario {
        val api=Api();api.failCreate="network_uncertain";val runtime=Runtime();val store=Store();val c=controller(api,runtime,store,this)
        c.connect("AUTO");await { c.status.value.phase==VpnPhase.CLEANUP_PENDING }
        c.beforeForget();assertNotNull(store.pending)
        // The caller has confirmed a successful server-side current-device revoke.
        c.confirmedDeviceRevocation()
        assertNull(store.pending);assertFalse(runtime.up);assertEquals(1,api.posts);assertEquals(VpnPhase.DISCONNECTED,c.status.value.phase)
    }
    @Test fun storageFailureAfterAllocationStillDeletesKnownServerSession() = scenario {
        val api=Api();val runtime=Runtime();val store=Store()
        // Initial reconcile + durable create intent succeed; persisting the received UUID fails.
        store.failAt=3
        val c=controller(api,runtime,store,this);c.connect("AUTO")
        await { c.status.value.phase==VpnPhase.FAILED }
        assertEquals(1,api.posts);assertTrue(api.deletes>0);assertNull(api.value);assertNull(store.pending);assertFalse(runtime.up)
    }
    @Test fun expiryUsesServerDurationRatherThanDeviceWallClock() = scenario {
        val api = Api(); val runtime = Runtime(); val store = Store()
        val remoteTime = Instant.parse("2040-01-01T00:00:00Z")
        val session = VpnSession(sessionId, "DE", remoteTime, remoteTime.plusSeconds(1), config)
        api.allocated = session
        val c = controller(api, runtime, store, this)
        c.connect("AUTO"); await { c.status.value.phase == VpnPhase.CONNECTED }
        await { c.status.value.phase in setOf(VpnPhase.DISCONNECTED,VpnPhase.FAILED) }
        assertFalse(runtime.up); assertNull(api.value); assertNull(store.pending)
    }
}
