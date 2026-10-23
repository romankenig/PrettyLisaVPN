package com.prettylisavpn.android.vpn

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

/** Cleanup outbox only; private WireGuard keys are ephemeral and never written to disk. */
class EncryptedVpnJournal(context: Context) : VpnJournal {
    private val file = AtomicFile(File(context.noBackupFilesDir, "vpn-cleanup.enc"))
    private val alias = "PrettyLisaVPN.vpn-cleanup.v1"
    private class Record(val entries: MutableMap<String, PendingVpn> = mutableMapOf())
    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(alias, null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).setKeySize(256).build())
        }.generateKey()
    }
    private fun all(): Record {
        if (!file.baseFile.exists() && !File(file.baseFile.path + ".bak").exists()) return Record()
        val bytes = file.readFully(); require(bytes.size in 29..65_536 && bytes[0] == 1.toByte())
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, bytes.copyOfRange(1, 13)))
        cipher.updateAAD(alias.toByteArray(Charsets.UTF_8))
        return Gson().fromJson(String(cipher.doFinal(bytes.copyOfRange(13, bytes.size)), Charsets.UTF_8), Record::class.java).also { record ->
            require(record.entries.size <= 100)
            record.entries.forEach { (owner, pending) -> UUID.fromString(owner); pending.id?.let { UUID.fromString(it) } }
        }
    }
    @Synchronized override fun read(owner: String): PendingVpn? = all().entries[owner]
    @Synchronized override fun write(owner: String, value: PendingVpn?) {
        UUID.fromString(owner)
        val record = all()
        if (value == null) record.entries.remove(owner) else record.entries[owner] = value
        val cipher = Cipher.getInstance("AES/GCM/NoPadding"); cipher.init(Cipher.ENCRYPT_MODE, key()); cipher.updateAAD(alias.toByteArray(Charsets.UTF_8))
        val bytes = byteArrayOf(1) + cipher.iv + cipher.doFinal(Gson().toJson(record).toByteArray(Charsets.UTF_8))
        require(bytes.size <= 65_536)
        val stream = file.startWrite()
        try { stream.write(bytes); file.finishWrite(stream) } catch (e: Exception) { file.failWrite(stream); throw e }
    }
}
