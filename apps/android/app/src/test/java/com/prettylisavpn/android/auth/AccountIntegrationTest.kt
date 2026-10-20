package com.prettylisavpn.android.auth

import com.prettylisavpn.android.data.*
import kotlinx.coroutines.*
import org.junit.Test
import org.junit.Assert.*
import java.util.UUID

private const val USER = "20000000-0000-0000-0000-000000000001"
private const val DEVICE = "20000000-0000-0000-0000-000000000002"
private const val MESSAGE = "20000000-0000-0000-0000-000000000003"
private const val OFFER = "20000000-0000-0000-0000-000000000004"
class AccountAuth : AuthApi {
    var id = USER
    var count = 2
    var revoked = false
    override suspend fun requestOtp(email: String) = Unit
    override suspend fun verifyOtp(email: String, code: String, installationId: String, deviceName: String) = tokens()
    private fun tokens() = Tokens("synthetic", 900, Credentials(DEVICE,"synthetic-refresh","2030-01-01T00:00:00Z"))
    override suspend fun refresh(credentials: Credentials) = tokens()
    override suspend fun me(access: String): Profile { if (revoked) throw AuthFailure("device_revoked"); return Profile("account@example.com","Premium",count,id) }
    override suspend fun logout(access: String) = Unit
}
class AccountPort(private val auth: AccountAuth) : AccountApi {
    var overview = BillingOverview("revision-1","DISABLED",false,"PREMIUM","ACTIVE","2030-01-01T00:00:00Z",true,"Bank card",null,routeIds.map { PaymentRoute(it,it,setOf("RUB","USD"),if(it in setOf("MIR","BANK_CARD")) setOf("RUB") else emptySet()) }, listOf(AccountOffer(OFFER,mapOf("RUB" to OfferPrice(10000),"USD" to OfferPrice(500)))),billingActions,null)
    var device = Device(DEVICE,"Other phone",false,"2026-10-20T00:00:00Z",null)
    var messages = listOf(AccountMessage(MESSAGE,3,"Message","Body","SUBSCRIPTION"))
    var ackError = false
    var listError = false
    var supportError = false
    var lookupError = false
    var billingTimeout = false
    var starts = mutableListOf<BillingIntent>()
    var submissions = mutableListOf<SupportSubmission>()
    var receipt: SupportReceipt? = null
    var operation = OperationReceipt(DEVICE,"PENDING")
    override suspend fun devices(token: String): List<Device> { if(listError) throw AuthFailure("offline"); return listOf(device) }
    override suspend fun revoke(token: String,id: String): Device { device=device.copy(active=false);auth.count=1;return device }
    override suspend fun messages(token: String): List<AccountMessage> { if(listError) throw AuthFailure("offline"); return messages }
    override suspend fun acknowledge(token: String,id: String,revision: Int) { if(ackError) throw AuthFailure("offline"); require(revision==3);messages=emptyList() }
    override suspend fun overview(token: String) = overview
    override suspend fun start(token: String,intent: BillingIntent): OperationReceipt { starts+=intent; if(billingTimeout) throw AuthFailure("network_uncertain");return operation }
    override suspend fun operation(token: String,id: String)=operation
    override suspend fun supportStatus(token: String,id: String): SupportReceipt? { if(lookupError) throw AuthFailure("offline");return receipt }
    override suspend fun supportSubmit(token: String,report: SupportSubmission): SupportReceipt { submissions+=report;if(supportError) throw AuthFailure("network_uncertain");return SupportReceipt(report.requestId,"ACCEPTED").also { receipt=it } }
}
class AccountIntegrationTest {
    private val auth=AccountAuth()
    private val port=AccountPort(auth)
    private val vault=MemoryVault().apply { value=Credentials(DEVICE,"fake","2030-01-01T00:00:00Z") }
    private val journal=MemoryJournal()
    private fun source()=LiveSessionSource(SessionCoordinator(auth,vault,"Test"),port,journal)
    private suspend fun failure(action:suspend()->Unit) { try { action(); fail("Expected failure") } catch (_: Exception) { } }
    @Test fun devicesRefreshProfileAndPreserveNullLogin()=runBlocking {
        val s=source();s.read(Area.SESSION);assertNull(s.read(Area.DEVICES).devices.single().lastLogin)
        val result=s.execute(Command.Revoke(DEVICE));assertEquals(1,result.activeDeviceCount);assertFalse(result.devices.single().active)
    }
    @Test fun currentDeviceRevokeClearsCredentials()=runBlocking {
        port.device=port.device.copy(current=true);val s=source();s.read(Area.SESSION)
        assertFalse(s.execute(Command.Revoke(DEVICE)).signedIn);assertNull(vault.value)
    }
    @Test fun failedAckKeepsMessageThenSuccessRefreshesQueue()=runBlocking {
        val s=source();s.read(Area.SESSION);s.read(Area.MESSAGES);port.ackError=true
        failure { s.execute(Command.Acknowledge(MESSAGE,3)) };assertEquals(1,s.initial.messages.size)
        port.ackError=false;assertTrue(s.execute(Command.Acknowledge(MESSAGE,3)).messages.isEmpty())
    }
    @Test fun staleRevisionNeverAcknowledgesNewMessage()=runBlocking {
        val s=source();s.read(Area.SESSION);s.read(Area.MESSAGES)
        failure { s.execute(Command.Acknowledge(MESSAGE,2)) };assertEquals(1,port.messages.size)
    }
    @Test fun successfulAckWithFailedRefreshDoesNotRepeatMutation()=runBlocking {
        val s=source();s.read(Area.SESSION);s.read(Area.MESSAGES);port.listError=true
        val result=s.execute(Command.Acknowledge(MESSAGE,3));assertTrue(result.messages.isEmpty());assertNotNull(result.refreshWarning)
    }
    @Test fun disabledAndSandboxNeverPostEvenWithMaliciousActions()=runBlocking {
        for(mode in listOf("DISABLED","SANDBOX")) {
            port.overview=port.overview.copy(mode=mode,available=true)
            val s=source();s.read(Area.SESSION);s.read(Area.BILLING)
            failure { s.execute(Command.Payment(UUID.randomUUID().toString(),"RENEW","MIR","RUB")) }
        }
        assertTrue(port.starts.isEmpty())
    }
    @Test fun changedPriceRequiresFreshConfirmation()=runBlocking {
        port.overview=port.overview.copy(mode="LIVE",available=true)
        val s=source();s.read(Area.SESSION);s.read(Area.BILLING);port.overview=port.overview.copy(revision="revision-2")
        failure { s.execute(Command.Payment(UUID.randomUUID().toString(),"RENEW","MIR","RUB")) };assertTrue(port.starts.isEmpty())
    }
    @Test fun lostPaymentResponseRetainsOriginalIntentAcrossRestart()=runBlocking {
        port.overview=port.overview.copy(mode="LIVE",available=true);port.billingTimeout=true
        val s=source();s.read(Area.SESSION);s.read(Area.BILLING)
        failure { s.execute(Command.Payment(UUID.randomUUID().toString(),"RENEW","MIR","RUB")) }
        val original=port.starts.single();assertNotNull(journal.read()!!.billing)
        port.billingTimeout=false;val next=source();next.read(Area.SESSION)
        next.execute(Command.Payment(UUID.randomUUID().toString(),"CANCEL","BANK_CARD","USD"))
        assertEquals(original,port.starts.last())
    }
    @Test fun supportLookupFailureNeverPosts()=runBlocking {
        val s=source();s.read(Area.SESSION);port.lookupError=true
        failure { s.execute(Command.Support(UUID.randomUUID().toString(),"Subject","Body","reply@example.com",0)) };assertTrue(port.submissions.isEmpty())
    }
    @Test fun supportLostResponseAndRestartReuseFrozenPayload()=runBlocking {
        val s=source();s.read(Area.SESSION);port.supportError=true
        failure { s.execute(Command.Support(UUID.randomUUID().toString(),"Subject","Original body","reply@example.com",0)) }
        val original=port.submissions.single();port.supportError=false
        val next=source();next.read(Area.SESSION)
        val result=next.execute(Command.Support(UUID.randomUUID().toString(),"Changed","Changed body","other@example.com",0))
        assertEquals(original,port.submissions.last());assertEquals("ACCEPTED",result.supportStatus)
    }
    @Test fun acceptedSupportIsNotSubmittedTwice()=runBlocking {
        val s=source();s.read(Area.SESSION)
        val command=Command.Support(UUID.randomUUID().toString(),"Subject","Body","reply@example.com",0)
        s.execute(command);s.execute(command);assertEquals(1,port.submissions.size)
    }
    @Test fun anotherAccountCannotRecoverPrivatePayload()=runBlocking {
        val s=source();s.read(Area.SESSION);port.supportError=true
        failure { s.execute(Command.Support(UUID.randomUUID().toString(),"Private subject","Private body","reply@example.com",0)) }
        auth.id=OFFER;val next=source();val result=next.read(Area.SESSION)
        assertFalse(result.supportFrozen);assertNull(journal.read())
    }
    @Test fun cancellationUsesNullOfferAndRetainsPaidDate()=runBlocking {
        port.overview=port.overview.copy(mode="LIVE",available=true);port.operation=port.operation.copy(status="SUCCEEDED")
        val s=source();s.read(Area.SESSION);s.read(Area.BILLING)
        val result=s.execute(Command.Payment(UUID.randomUUID().toString(),"CANCEL","MIR","RUB"))
        assertNull(port.starts.single().offer_id);assertNull(port.starts.single().payment_route);assertEquals("2030-01-01T00:00:00Z",result.paidUntil)
    }
}
