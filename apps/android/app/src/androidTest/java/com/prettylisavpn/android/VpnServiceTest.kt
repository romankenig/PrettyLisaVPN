package com.prettylisavpn.android

import android.app.NotificationManager
import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.VpnService
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Column
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import com.prettylisavpn.android.auth.*
import com.prettylisavpn.android.ui.*
import com.prettylisavpn.android.vpn.*
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.delay
import kotlinx.coroutines.withTimeout
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.time.Instant

/** Real user consent, foreground service, JNI/TUN and revoke. Only the server port is synthetic.
 * An unresponsive WireGuard peer MUST NEVER produce Connected, even though Android has a VPN.
 */
class VpnServiceTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()
    @Test fun realConsentNativeTunnelNotificationAndRevokeCleanUpWithoutFalseConnected() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val app = instrumentation.targetContext
        val device = UiDevice.getInstance(instrumentation)
        val owner = "d84cd4d2-8aee-4c17-9772-31db1d512924"
        val sessionId = "28d1564f-cb6e-4d0c-b2a6-b6db50b0fca1"
        val vault = object : CredentialVault {
            override fun read() = Credentials(owner,"synthetic","2040-01-01T00:00:00Z")
            override fun write(credentials: Credentials) = Unit
            override fun clear() = Unit
            override fun installationId() = owner
        }
        val auth = object : AuthApi {
            override suspend fun requestOtp(email: String) = error("no email allowed")
            override suspend fun verifyOtp(email: String, code: String, installationId: String, deviceName: String): Tokens = error("no OTP allowed")
            override suspend fun refresh(credentials: Credentials) = Tokens("synthetic",3600,credentials)
            override suspend fun me(access: String) = Profile("vpn@example.com","Free",1,owner)
            override suspend fun logout(access: String) = Unit
        }
        val sessions = SessionCoordinator(auth,vault,"isolated emulator")
        runBlocking { sessions.restore() }
        val directory=File(app.getExternalFilesDir(null),"acceptance/vpn").apply { mkdirs() }
        val bridge=File(app.filesDir,"vpn-test-peer").apply { mkdirs() }
        var realPeer = false
        var posts = 0; var deletes = 0; var current: VpnSession? = null
        val api = object : VpnApi {
            override suspend fun current() = current
            override suspend fun create(country: String, publicKey: String): VpnSession {
                assertEquals("DE",country); assertTrue(publicKey.length==44); posts++
                val serverKey = if (realPeer) {
                    File(bridge,"peer-ready").delete()
                    File(bridge,"client-public-key.tmp").writeText(publicKey)
                    check(File(bridge,"client-public-key.tmp").renameTo(File(bridge,"client-public-key")))
                    withTimeout(10_000) { while(!File(bridge,"peer-ready").exists()) delay(100) }
                    File(bridge,"server-public-key").readText().trim()
                } else "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE="
                val working = VpnConfig("198.18.0.1",51820,serverKey,"10.77.0.2/32",listOf("1.1.1.1"))
                // Exercise real native stop/restart before a later candidate wins.
                val candidates = if (realPeer) listOf(working.copy(port=51821),working) else listOf(working)
                return VpnSession(sessionId,"DE",Instant.now(),null,candidates.first(),candidates).also { current = it }
            }
            override suspend fun delete(id: String) {
                assertEquals(sessionId,id); deletes++
                if (realPeer) {
                    File(bridge,"peer-removed").delete()
                    File(bridge,"remove-peer").writeText("remove")
                    withTimeout(10_000) { while(!File(bridge,"peer-removed").exists()) delay(100) }
                }
                current=null
            }
        }
        val journal = EncryptedVpnJournal(app)
        journal.write(owner,null)
        val host = AndroidVpnHost.create(app,sessions,HttpAuthApi("https://unused.invalid/"),api,journal)
        compose.runOnUiThread { compose.activity.setContent { PrettyLisaTheme { LocalizedApp { Column { VpnControls(host,"DE",true) } } } } }
        fun click() { compose.waitForIdle(); compose.onNodeWithTag("home-connect").performClick() }
        fun clickSystemDialog(selector: androidx.test.uiautomator.BySelector) {
            val button = device.wait(Until.findObject(selector.enabled(true).clickable(true)),10_000)
            assertNotNull("system consent button",button)
            val packageName = button.applicationPackage
            // Accessibility exposes the button before WindowManager finishes making its
            // window focusable. A click in that interval is silently lost on API 35/36.
            compose.waitUntil(10_000) {
                instrumentation.uiAutomation.windows.any {
                    it.isFocused && it.root?.packageName?.toString() == packageName
                }
            }
            device.waitForIdle()
            val ready = device.findObject(selector)
            assertNotNull("focused system consent button",ready)
            ready.click()
            assertTrue("system consent dialog dismissed",device.wait(Until.gone(selector),10_000))
        }
        fun consent(accept: Boolean) {
            if (VpnService.prepare(app) == null) return
            val name = if (accept) "android:id/button1" else "android:id/button2"
            clickSystemDialog(By.pkg("com.android.vpndialogs").res(name))
        }
        // First reject the actual Android VPN consent. There must be no backend allocation.
        if (VpnService.prepare(app) != null) {
            click(); consent(false)
            compose.waitUntil(10_000) { compose.onAllNodesWithTag("vpn-error").fetchSemanticsNodes().isNotEmpty() }
            assertEquals(0,posts); assertNull(current)
        }
        click(); consent(true)
        // Notification consent is independent. Accept on Android 13+, if it is shown.
        if (android.os.Build.VERSION.SDK_INT >= 33 && app.checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            // Google system images may use a different resource namespace from AOSP.
            clickSystemDialog(By.res(java.util.regex.Pattern.compile(".*:id/permission_allow_button")))
            compose.waitUntil(10_000) { app.checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) == android.content.pm.PackageManager.PERMISSION_GRANTED }
        }
        compose.waitUntil(15_000) { host.status.value.phase in setOf(VpnPhase.VERIFYING,VpnPhase.CONNECTED,VpnPhase.FAILED) }
        assertEquals("VPN status: ${host.status.value}",VpnPhase.VERIFYING,host.status.value.phase)
        assertEquals(1,posts)
        val manager = app.getSystemService(ConnectivityManager::class.java)
        compose.waitUntil(10_000) { manager.allNetworks.any { manager.getNetworkCapabilities(it)?.hasTransport(NetworkCapabilities.TRANSPORT_VPN)==true } }
        val network = manager.allNetworks.first { manager.getNetworkCapabilities(it)?.hasTransport(NetworkCapabilities.TRANSPORT_VPN)==true }
        assertTrue(manager.getLinkProperties(network)!!.linkAddresses.any { it.address.hostAddress=="172.30.255.1" })
        val notifications=app.getSystemService(NotificationManager::class.java)
        compose.waitUntil(10_000) { notifications.activeNotifications.any { it.notification.extras.getString("android.title")=="PrettyLisaVPN" } }
        compose.waitForIdle()
        instrumentation.uiAutomation.executeShellCommand("screencap -p").use { fd -> File(directory,"verifying-real-tun.png").outputStream().use { out -> android.os.ParcelFileDescriptor.AutoCloseInputStream(fd).copyTo(out) } }
        // Explicit stop of the failed peer must remove native state and the server session.
        click()
        compose.waitUntil(15_000) { host.status.value.phase == VpnPhase.DISCONNECTED }
        assertNull(current); assertNull(journal.read(owner))
        compose.waitUntil(10_000) { manager.allNetworks.none { manager.getNetworkCapabilities(it)?.hasTransport(NetworkCapabilities.TRANSPORT_VPN)==true } }
        // A real ephemeral WireGuard peer on this CI runner now serves DNS/HTTPS through NAT.
        realPeer = true
        compose.waitForIdle()
        compose.onNodeWithTag("home-connect").assertTextEquals(compose.activity.getString(R.string.dash_connect))
        click()
        compose.waitUntil(10_000) { posts == 2 || host.status.value.error != null }
        assertEquals("second start: ${host.status.value}",2,posts)
        compose.waitUntil(75_000) { host.status.value.phase in setOf(VpnPhase.CONNECTED,VpnPhase.FAILED,VpnPhase.CLEANUP_PENDING) }
        assertEquals("VPN status: ${host.status.value}",VpnPhase.CONNECTED,host.status.value.phase)
        assertEquals(2,posts)
        compose.waitForIdle()
        instrumentation.uiAutomation.executeShellCommand("screencap -p").use { fd -> File(directory,"connected-real-peer.png").outputStream().use { out -> android.os.ParcelFileDescriptor.AutoCloseInputStream(fd).copyTo(out) } }
        if (InstrumentationRegistry.getArguments().getString("vpnStage") == "seed") {
            assertEquals(sessionId,journal.read(owner)!!.id)
            File(directory,"restart-seed.txt").writeText("source_sha=${BuildConfig.SOURCE_SHA}\nconnected=true\ncleanup_persisted=true\n")
            return // CI force-stops this process, retaining the isolated server peer for the next process.
        }
        // System revocation is delivered to the production service via onRevoke.
        compose.runOnUiThread { compose.activity.startActivity(android.content.Intent(android.provider.Settings.ACTION_VPN_SETTINGS)) }
        val preference = device.wait(Until.findObject(By.text("PrettyLisaVPN")),10_000)
        assertNotNull("system VPN settings list",preference)
        preference.click()
        val revoke = device.wait(Until.findObject(By.text(java.util.regex.Pattern.compile("(?i)(disconnect|forget)"))),5_000)
        assertNotNull("system disconnect action",revoke)
        revoke.click()
        compose.waitUntil(15_000) { host.status.value.phase in setOf(VpnPhase.DISCONNECTED,VpnPhase.FAILED) }
        assertTrue(deletes>0); assertNull(current); assertNull(journal.read(owner))
        compose.waitUntil(10_000) { manager.allNetworks.none { manager.getNetworkCapabilities(it)?.hasTransport(NetworkCapabilities.TRANSPORT_VPN)==true } }
        assertNotEquals(VpnPhase.CONNECTED,host.status.value.phase)
        File(directory,"result.txt").writeText("source_sha=${BuildConfig.SOURCE_SHA}\nreal_consent=true\nreal_foreground_service=true\nreal_jni_tun=true\nunresponsive_peer_connected=false\nreal_ephemeral_peer_connected=true\nVPN_bound_DNS_HTTPS=true\nserver_cleanup=true\nrevoke=true\n")
        device.pressBack()
    }
}
