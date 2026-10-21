package com.prettylisavpn.android.auth

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.AtomicFile
import com.google.gson.Gson
import java.io.File
import java.security.KeyStore
import java.util.UUID
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** AES-GCM authenticates the whole record. AtomicFile is confined to noBackupFilesDir.
 * No biometric requirement: restoration must work after normal process restart.
 */
class KeystoreVault(context: Context) : CredentialVault {
    private val app = context.applicationContext
    private val record = AtomicFile(File(context.noBackupFilesDir, "session.enc"))
    private val installation = AtomicFile(File(context.noBackupFilesDir, "installation.id"))
    private val gson = Gson()
    private val alias = "PrettyLisaVPN.session.v1"
    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(alias, null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256).build())
        }.generateKey()
    }
    private fun atomicWrite(file: AtomicFile, bytes: ByteArray) {
        val stream = file.startWrite()
        try { stream.write(bytes); file.finishWrite(stream) } catch (failure: Exception) { file.failWrite(stream); throw failure }
    }
    @Synchronized override fun read(): Credentials? {
        if (!record.baseFile.exists() && !File(record.baseFile.path + ".bak").exists()) return null
        val bytes = record.readFully(); require(bytes.size in 30..8192 && bytes[0] == 1.toByte())
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, bytes.copyOfRange(1, 13)))
        cipher.updateAAD(alias.toByteArray(Charsets.UTF_8))
        val value = gson.fromJson(String(cipher.doFinal(bytes.copyOfRange(13, bytes.size)), Charsets.UTF_8), Credentials::class.java)
        UUID.fromString(value.sessionId); java.time.Instant.parse(value.expiresAt)
        require(value.refreshToken.isNotBlank() && value.refreshToken.length <= 512)
        return value
    }
    @Synchronized override fun write(credentials: Credentials) {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key()); cipher.updateAAD(alias.toByteArray(Charsets.UTF_8))
        atomicWrite(record, byteArrayOf(1) + cipher.iv + cipher.doFinal(gson.toJson(credentials).toByteArray(Charsets.UTF_8)))
    }
    @Synchronized override fun clear() {
        record.delete()
        check(!record.baseFile.exists() && !File(record.baseFile.path + ".bak").exists())
    }
    @android.annotation.SuppressLint("HardwareIds") // Scoped Android ID only seeds the app installation UUID; never sent raw.
    @Synchronized override fun installationId(): String {
        if (installation.baseFile.exists() || File(installation.baseFile.path + ".bak").exists()) return String(installation.readFully(), Charsets.UTF_8).also { UUID.fromString(it) }
        // ANDROID_ID is scoped to this signing key, Android user and device. Keep the
        // existing installation UUID first, so upgrades never create a new server device.
        val scoped = android.provider.Settings.Secure.getString(app.contentResolver, android.provider.Settings.Secure.ANDROID_ID)
        val id = if (scoped != null && scoped.matches(Regex("[0-9a-fA-F]{16}")) && scoped != "9774d56d682e549c")
            UUID.nameUUIDFromBytes((app.packageName + ":installation:v2:" + scoped).toByteArray(Charsets.UTF_8)).toString()
        else UUID.randomUUID().toString()
        return id.also { atomicWrite(installation, it.toByteArray(Charsets.UTF_8)) }
    }
}
