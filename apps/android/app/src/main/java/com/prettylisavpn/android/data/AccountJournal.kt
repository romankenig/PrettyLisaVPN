package com.prettylisavpn.android.data

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.AtomicFile
import com.google.gson.Gson
import java.io.File
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Sensitive support text/files are encrypted and never restored into another account. */
data class AccountJournal(val owner: String, val support: SupportSubmission? = null, val supportReceipt: SupportReceipt? = null, val billing: BillingIntent? = null, val operation: OperationReceipt? = null)
interface JournalStore { fun read(): AccountJournal?; fun write(value: AccountJournal); fun clear() }
class MemoryJournal : JournalStore {
    private var value: AccountJournal? = null
    override fun read() = value
    override fun write(value: AccountJournal) { this.value = value }
    override fun clear() { value = null }
}
class EncryptedJournal(context: Context) : JournalStore {
    private val file = AtomicFile(File(context.noBackupFilesDir, "account-operations.enc"))
    private val alias = "PrettyLisaVPN.account-operations.v1"
    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(alias, null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).setKeySize(256).build())
        }.generateKey()
    }
    @Synchronized override fun read(): AccountJournal? {
        if (!file.baseFile.exists() && !File(file.baseFile.path + ".bak").exists()) return null
        val bytes = file.readFully(); require(bytes.size in 29..20_000_000 && bytes[0] == 1.toByte())
        val cipher = Cipher.getInstance("AES/GCM/NoPadding"); cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, bytes.copyOfRange(1,13)))
        cipher.updateAAD(alias.toByteArray()); return Gson().fromJson(String(cipher.doFinal(bytes.copyOfRange(13,bytes.size)), Charsets.UTF_8), AccountJournal::class.java)
    }
    @Synchronized override fun write(value: AccountJournal) {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding"); cipher.init(Cipher.ENCRYPT_MODE, key()); cipher.updateAAD(alias.toByteArray())
        val bytes = byteArrayOf(1) + cipher.iv + cipher.doFinal(Gson().toJson(value).toByteArray(Charsets.UTF_8))
        require(bytes.size <= 20_000_000)
        val stream = file.startWrite()
        try { stream.write(bytes); file.finishWrite(stream) } catch (failure: Exception) { file.failWrite(stream); throw failure }
    }
    @Synchronized override fun clear() { file.delete(); check(!file.baseFile.exists() && !File(file.baseFile.path + ".bak").exists()) }
}
