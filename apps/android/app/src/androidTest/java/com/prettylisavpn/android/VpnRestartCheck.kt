package com.prettylisavpn.android

import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import androidx.test.platform.app.InstrumentationRegistry
import com.prettylisavpn.android.vpn.*
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.time.Instant

class VpnRestartCheck {
    @Test fun freshProcessCleansDurableSessionWithoutRestoringVpnOrReposting() = runBlocking {
        val app=InstrumentationRegistry.getInstrumentation().targetContext
        val owner="d84cd4d2-8aee-4c17-9772-31db1d512924"
        val id="28d1564f-cb6e-4d0c-b2a6-b6db50b0fca1"
        assertNull(AndroidVpnHost.instance)
        val journal=EncryptedVpnJournal(app)
        assertEquals(id,journal.read(owner)!!.id)
        val encrypted=File(app.noBackupFilesDir,"vpn-cleanup.enc").readBytes().toString(Charsets.ISO_8859_1)
        assertFalse(encrypted.contains(id));assertFalse(encrypted.contains(owner))
        var current: VpnSession?=VpnSession(id,"DE",Instant.now(),null,null)
        val directory=File(app.getExternalFilesDir(null),"acceptance/vpn")
        val api=object:VpnApi {
            override suspend fun current()=current
            override suspend fun create(country:String,publicKey:String):VpnSession=error("restart must not POST")
            override suspend fun delete(id:String) {
                assertEquals(current!!.id,id)
                File(directory,"peer-removed").delete();File(directory,"remove-peer").writeText("remove")
                withTimeout(10_000) { while(!File(directory,"peer-removed").exists())delay(100) }
                current=null
            }
        }
        var stops=0
        val runtime=object:TunnelRuntime {
            override suspend fun start(config:VpnConfig,key:TunnelKey)=error("restart must not restart tunnel")
            override suspend fun stop() { stops++ }
            override suspend fun verify(config:VpnConfig)=false
        }
        val scope=CoroutineScope(SupervisorJob()+Dispatchers.Default)
        try {
            val c=VpnController(api,runtime,journal,{ owner },{ error("restart must not generate keys") },scope,{ android.os.SystemClock.elapsedRealtime() })
            c.recover()
            assertEquals(VpnPhase.DISCONNECTED,c.status.value.phase);assertNull(journal.read(owner));assertNull(current);assertTrue(stops>0)
            val manager=app.getSystemService(ConnectivityManager::class.java)
            withTimeout(10_000) { while(manager.allNetworks.any { manager.getNetworkCapabilities(it)?.hasTransport(NetworkCapabilities.TRANSPORT_VPN)==true })delay(100) }
            File(directory,"restart-check.txt").writeText("source_sha=${BuildConfig.SOURCE_SHA}\nnew_process=true\nVPN_closed_by_OS=true\nserver_peer_removed=true\nnew_POST=false\nconnected=false\n")
        } finally { scope.cancel() }
    }
}
