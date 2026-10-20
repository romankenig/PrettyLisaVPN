package com.prettylisavpn.android

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.prettylisavpn.android.data.*
import org.junit.*
import org.junit.Assert.*
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class AccountJournalTest {
    private val context get()=InstrumentationRegistry.getInstrumentation().targetContext
    @After fun clear() { EncryptedJournal(context).clear() }
    @Test fun encryptedPayloadAndIntentSurviveNewInstance() {
        val value=AccountJournal("test-owner",SupportSubmission("request-id","private subject","private body","reply@example.com",emptyList()),billing=BillingIntent("billing-id","CANCEL","revision",null,null,"RUB"))
        EncryptedJournal(context).write(value)
        val bytes=File(context.noBackupFilesDir,"account-operations.enc").readBytes()
        assertFalse(String(bytes,Charsets.ISO_8859_1).contains("private body"))
        assertEquals(value,EncryptedJournal(context).read())
    }
    @Test fun tamperFailsClosedAndClearRemovesRecord() {
        val journal=EncryptedJournal(context);journal.write(AccountJournal("owner"))
        val file=File(context.noBackupFilesDir,"account-operations.enc");val bytes=file.readBytes();bytes[bytes.lastIndex]=(bytes.last().toInt() xor 1).toByte();file.writeBytes(bytes)
        try { journal.read();fail() } catch(_:Exception) { }
        journal.clear();assertNull(journal.read())
    }
}
