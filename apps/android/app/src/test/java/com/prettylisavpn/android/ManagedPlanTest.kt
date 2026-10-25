package com.prettylisavpn.android

import com.google.gson.JsonParser
import com.prettylisavpn.android.auth.AuthFailure
import com.prettylisavpn.android.vpn.*
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test
import java.time.Instant

class ManagedPlanTest {
    private val base = VpnConfig("203.0.113.1",51820,"AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE=","10.77.0.2/32",listOf("1.1.1.1"))
    private val session = VpnSession("d84cd4d2-8aee-4c17-9772-31db1d512924","DE",Instant.parse("2026-10-22T00:00:00Z"),null,base)
    private fun fixture() = JsonParser.parseString(javaClass.getResource("/plan-v1.json")!!.readText()).asJsonObject
    @Test fun completePlanKeepsWireGuardThenEveryServerCandidateAndNoSecretsInStatus() {
        val result = parseManagedPlan(fixture(),session)
        assertEquals(21,result.candidates.size)
        assertEquals(VpnMethod.WIREGUARD_UDP,result.candidates.first().method)
        assertEquals((18443..18462).toList(),result.candidates.drop(1).map { it.port })
        assertEquals(21,result.candidates.map { it.method }.distinct().size)
        assertFalse(result.toString().contains("463bb488"))
        for (mutation in listOf<(com.google.gson.JsonObject)->Unit>(
            { it.getAsJsonArray("profiles")[1].asJsonObject.remove("certificate_pin") },
            { it.getAsJsonArray("profiles")[1].asJsonObject.addProperty("insecure",true) },
            { it.getAsJsonArray("profiles")[1].asJsonObject.addProperty("method","DIRECT") },
            { it.getAsJsonArray("profiles")[1].asJsonObject.addProperty("server","127.0.0.1") },
            { it.getAsJsonArray("profiles").add(it.getAsJsonArray("profiles")[0].deepCopy()) },
            { it.addProperty("expires_at","2026-10-22T00:30:00Z") }
        )) {
            try { parseManagedPlan(fixture().also(mutation),session); fail("unsafe plan accepted") }
            catch (failure:AuthFailure) { assertEquals("invalid_response",failure.code) }
        }
    }
    @Test fun allFailedCandidatesAreStoppedBeforeNextAndLastCanWin() = runBlocking {
        for (success in listOf(true,false)) {
            val plan = parseManagedPlan(fixture(),session).copy(expiresAt=null)
            val scope=CoroutineScope(SupervisorJob()+Dispatchers.Default)
            var current: VpnSession?=null; var posts=0; var deletes=0
            val api=object:VpnApi {
                override suspend fun current()=current
                override suspend fun create(country:String,publicKey:String):VpnSession { posts++;current=plan;return plan }
                override suspend fun delete(id:String) { deletes++;current=null }
            }
            val attempted=mutableListOf<VpnMethod>();var up=false
            val runtime=object:TunnelRuntime {
                override suspend fun start(config:VpnConfig,key:TunnelKey) { check(!up);up=true;attempted.add(config.method) }
                override suspend fun stop() { up=false }
                override suspend fun verify(config:VpnConfig):Boolean = success && attempted.size==21
            }
            val journal=object:VpnJournal {
                var value:PendingVpn?=null
                override fun read(owner:String)=value
                override fun write(owner:String,value:PendingVpn?) {this.value=value}
            }
            val c=VpnController(api,runtime,journal,{"owner"},{object:TunnelKey {override val publicKey="synthetic"}},scope,{System.nanoTime()/1_000_000},attemptMillis=10)
            try {
                c.connect("DE")
                withTimeout(5_000) {while(c.status.value.phase !in setOf(VpnPhase.CONNECTED,VpnPhase.FAILED)) delay(5)}
                assertEquals(plan.candidates.map {it.method},attempted);assertEquals(1,posts)
                if(success) {assertEquals(plan.candidates.last().method,c.status.value.method);assertEquals(0,deletes);c.beforeLogout()}
                else {assertEquals(1,deletes);assertNull(c.status.value.method);assertFalse(up);assertNull(journal.value)}
            } finally {scope.cancel()}
        }
    }
}
