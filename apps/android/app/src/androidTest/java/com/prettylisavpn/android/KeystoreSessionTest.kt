package com.prettylisavpn.android

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.prettylisavpn.android.auth.*
import java.io.File
import org.junit.*
import org.junit.Assert.*
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class KeystoreSessionTest {
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext
    private val record get() = File(context.noBackupFilesDir, "session.enc")
    private val credential = Credentials("c21132ac-0d2e-4da7-96ac-8a6ceeb019ba", "test-sensitive-refresh", "2030-01-01T00:00:00Z")
    @Before fun clearBefore() { KeystoreVault(context).clear() }
    @After fun clearAfter() { KeystoreVault(context).clear() }
    @Test fun encryptedRecordSurvivesNewVaultInstance() {
        KeystoreVault(context).write(credential)
        assertFalse(String(record.readBytes(), Charsets.ISO_8859_1).contains(credential.refreshToken))
        assertEquals(credential, KeystoreVault(context).read())
        val first = record.readBytes(); KeystoreVault(context).write(credential)
        assertFalse(first.contentEquals(record.readBytes())) // fresh GCM nonce
    }
    @Test fun pendingRotationSurvivesRestartAndClearRetainsInstallation() {
        val vault = KeystoreVault(context); val installation = vault.installationId()
        vault.write(credential.copy(rotationPending = true))
        assertTrue(KeystoreVault(context).read()!!.rotationPending)
        KeystoreVault(context).clear(); assertNull(vault.read())
        assertEquals(installation, KeystoreVault(context).installationId())
    }
    @Test fun tamperedCiphertextFailsAuthentication() {
        KeystoreVault(context).write(credential)
        val bytes = record.readBytes(); bytes[bytes.lastIndex] = (bytes.last().toInt() xor 1).toByte(); record.writeBytes(bytes)
        try { KeystoreVault(context).read(); fail("Tampering must fail closed") } catch (_: javax.crypto.AEADBadTagException) { }
    }
}
